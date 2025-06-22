#!/usr/bin/env python3
"""
File Transfer Server disguised as HTTP server
Handles file uploads through HTTP requests with parallel processing
"""

import os
import json
import hashlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import tempfile
import shutil
from collections import defaultdict
import logging
import signal
import sys


from .cipher import DFPCipher

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DFPHandler(BaseHTTPRequestHandler):
   
    # Class variables to store session data
    sessions = {}
    session_lock = threading.Lock()
    cipher = None
    enable_encryption = False
    
    def __init__(self, *args, **kwargs):
        self.max_workers = 5  # Reduced from 10 to prevent connection overload
        super().__init__(*args, **kwargs)
    
    def log_message(self, format, *args):
        """Override to use our logger instead of stderr"""
        logger.info(f"{self.address_string()} - {format % args}")
    
    def do_GET(self):
        """Handle GET requests for session creation"""
        try:
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            
            if path == '/cs':
                self._handle_create_session(parsed_url.query)
            elif path == '/status':
                self._handle_status(parsed_url.query)
            else:
                self._send_error_response(404, "Not Found")
                
        except Exception as e:
            logger.error(f"Error in GET request: {e}")
            self._send_error_response(500, f"Internal Server Error: {str(e)}")
    
    def do_POST(self):
        """Handle POST requests for file chunk uploads"""
        try:
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            
            if path == '/k':
                self._handle_upload_chunk()
            elif path == '/fs':
                self._handle_complete_session()
            else:
                self._send_error_response(404, "Not Found")
                
        except Exception as e:
            logger.error(f"Error in POST request: {e}")
            self._send_error_response(500, f"Internal Server Error: {str(e)}")
    
    def _authenticate_sign(self, sign):
        import base64
        try:
            # Decrypt the sign
            decrypted_timestamp = float(self.cipher.decrypt(
                base64.b64decode(sign.encode()), parallel_size=1
            ))
            # Check if timestamp is within +/- 10 seconds
            current_time = time.time()
            logger.debug(f"Client Timestamp {decrypted_timestamp}, Server Timestamp {current_time}")
            return abs(current_time - decrypted_timestamp) <= 30
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False
    
    def _handle_create_session(self, query_string):
        """Create a new file transfer session"""
        import base64
        try:
            params = parse_qs(query_string)
            sign = params.get('g', [''])[0]
            if not self._authenticate_sign(sign):
                self._send_json_response(403, {"error": "Authentication failed"})
                return

            filename = params.get('f', [''])[0]
            # always encrypt filename
            filename = base64.b64decode(filename)
            filename = self.cipher.decrypt(filename, decode=True, parallel_size=1) 
            total_size = int(params.get('s', [0])[0])
            total_chunks = int(params.get('c', [0])[0])
            file_hash = params.get('h', [''])[0]
            
            if not filename or total_size <= 0 or total_chunks <= 0:
                self._send_error_response(400, "Missing or invalid parameters")
                return
            
            # Generate session ID
            session_id = hashlib.md5(f"{filename}{time.time()}".encode()).hexdigest()[:16]
            
            # Create session directory
            session_dir = os.path.join(tempfile.gettempdir(), f"file_transfer_{session_id}")
            os.makedirs(session_dir, exist_ok=True)
            
            # Initialize session data
            with self.session_lock:
                self.sessions[session_id] = {
                    'filename': filename,
                    'total_size': total_size,
                    'total_chunks': total_chunks,
                    'file_hash': file_hash,
                    'session_dir': session_dir,
                    'received_chunks': set(),
                    'chunk_files': {},
                    'start_time': time.time(),
                    'status': 'active',
                    'last_activity': time.time()
                }
            
            logger.info(f"Created session {session_id} for file {filename} ({total_chunks} chunks)")
            
            response = {
                'session_id': session_id,
                'status': 'created',
                'message': 'Session created successfully'
            }
            
            self._send_json_response(200, response)
            
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            self._send_error_response(500, f"Failed to create session: {str(e)}")
    
    def _handle_upload_chunk(self):
        """Handle file chunk upload with improved error handling"""
        try:
            # Get content length
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._send_error_response(400, "No content")
                return
            
            # Read request body with timeout protection
            try:
                body = self.rfile.read(content_length)
            except Exception as e:
                logger.error(f"Error reading request body: {e}")
                self._send_error_response(400, "Failed to read request body")
                return
            
            # Parse chunk data (assuming JSON format)
            try:
                chunk_data = json.loads(body.decode('utf-8'))
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in request: {e}")
                self._send_error_response(400, "Invalid JSON format")
                return
            
            session_id = chunk_data.get('session_id')
            chunk_index = chunk_data.get('chunk_index')
            chunk_data_b64 = chunk_data.get('chunk_data')
            
            if not session_id or chunk_index is None or not chunk_data_b64:
                self._send_error_response(400, "Missing chunk parameters")
                return
            
            # Check if session exists and is active
            with self.session_lock:
                if session_id not in self.sessions:
                    self._send_error_response(404, "Session not found")
                    return
                
                session = self.sessions[session_id]
                if session['status'] != 'active':
                    self._send_error_response(400, "Session not active")
                    return
                
                # Update last activity
                session['last_activity'] = time.time()
            
            # Process chunk with timeout
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(self._process_chunk, session_id, chunk_index, chunk_data_b64)
                    result = future.result(timeout=30)  # 30 second timeout
                    
                    if result['success']:
                        self._send_json_response(200, {
                            'status': 'success',
                            'chunk_index': chunk_index,
                            'message': 'Chunk uploaded successfully'
                        })
                    else:
                        self._send_error_response(500, result['error'])
                        
            except Exception as e:
                logger.error(f"Error processing chunk: {e}")
                self._send_error_response(500, f"Failed to process chunk: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error uploading chunk: {e}")
            self._send_error_response(500, f"Failed to upload chunk: {str(e)}")
    
    def _process_chunk(self, session_id, chunk_index, chunk_data_b64):
        """Process a single chunk (runs in parallel)"""
        try:
            import base64
            
            # Check if session exists
            with self.session_lock:
                if session_id not in self.sessions:
                    return {'success': False, 'error': 'Session not found'}
                
                session = self.sessions[session_id]
                if session['status'] != 'active':
                    return {'success': False, 'error': 'Session not active'}
            
            # Decode chunk data
            try:
                chunk_data = base64.b64decode(chunk_data_b64)
            except Exception as e:
                return {'success': False, 'error': f'Invalid base64 data: {str(e)}'}
            
            # Save chunk to temporary file
            chunk_filename = os.path.join(session['session_dir'], f"chunk_{chunk_index:06d}")
            try:
                with open(chunk_filename, 'wb') as f:
                    f.write(chunk_data)
            except Exception as e:
                return {'success': False, 'error': f'Failed to save chunk: {str(e)}'}
            
            # Update session data
            with self.session_lock:
                session['received_chunks'].add(chunk_index)
                session['chunk_files'][chunk_index] = chunk_filename
                session['last_activity'] = time.time()
            
            logger.debug(f"Processed chunk {chunk_index} for session {session_id}")
            return {'success': True}
            
        except Exception as e:
            logger.error(f"Error processing chunk {chunk_index}: {e}")
            return {'success': False, 'error': str(e)}
    
    def _handle_complete_session(self):
        """Complete the file transfer session and reconstruct the file"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._send_error_response(400, "No content")
                return
            
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            session_id = data.get('session_id')
            
            if not session_id:
                self._send_error_response(400, "Missing session_id")
                return
            
            # Complete session with timeout
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(self._finalize_session, session_id)
                    result = future.result(timeout=60)  # 60 second timeout
                    
                    if result['success']:
                        self._send_json_response(200, {
                            'status': 'completed',
                            'fp': result['file_path'],
                            'message': 'completed successfully'
                        })
                    else:
                        self._send_error_response(500, result['error'])
                        
            except Exception as e:
                logger.error(f"Error completing session: {e}")
                self._send_error_response(500, f"Failed to complete session: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error completing session: {e}")
            self._send_error_response(500, f"Failed to complete session: {str(e)}")
    
    def _finalize_session(self, session_id):
        """Finalize session and reconstruct the file (runs in parallel)"""
        try:
            with self.session_lock:
                if session_id not in self.sessions:
                    return {'success': False, 'error': 'Session not found'}
                
                session = self.sessions[session_id]
                if session['status'] != 'active':
                    return {'success': False, 'error': 'Session not active'}
                
                # Mark session as finalizing
                session['status'] = 'finalizing'
            
            # Check if all chunks are received
            if len(session['received_chunks']) != session['total_chunks']:
                missing_chunks = set(range(session['total_chunks'])) - session['received_chunks']
                return {'success': False, 'error': f'Missing chunks: {missing_chunks}'}
            
            # Reconstruct file
            os.makedirs(os.path.join(os.getcwd(), 'dfp_received'), exist_ok=True)
            output_path = os.path.join(os.getcwd(), 'dfp_received', session['filename'])
            

            try:
                with open(output_path, 'wb') as output_file:
                    for i in range(session['total_chunks']):
                        chunk_file = session['chunk_files'][i]
                        with open(chunk_file, 'rb') as chunk_f:
                            chunk_data = chunk_f.read()
                            if self.enable_encryption:
                                start_time = time.time()
                                logger.debug("Decrypting current chunk")
                                chunk_data = self.cipher.decrypt(chunk_data, parallel_size=os.cpu_count())
                                logger.debug(f"Chunk decrypted, took {time.time() - start_time}s")
                            output_file.write(chunk_data)
            except Exception as e:
                return {'success': False, 'error': f'Failed to reconstruct file: {str(e)}'}
            
            # Verify file hash if provided
            if session['file_hash']:
                try:
                    with open(output_path, 'rb') as f:
                        calculated_hash = hashlib.md5(f.read()).hexdigest()
                        if calculated_hash != session['file_hash']:
                            os.remove(output_path)
                            return {'success': False, 'error': 'File hash verification failed'}
                except Exception as e:
                    return {'success': False, 'error': f'Failed to verify file hash: {str(e)}'}
            
            # Clean up session
            with self.session_lock:
                session['status'] = 'completed'
                session['end_time'] = time.time()
                session['file_path'] = output_path
            
            # Clean up temporary files
            try:
                shutil.rmtree(session['session_dir'])
            except Exception as e:
                logger.warning(f"Failed to clean up session directory: {e}")
            
            transfer_time = session['end_time'] - session['start_time']
            logger.info(f"Session {session_id} completed. File: {session['filename']}, "
                       f"Size: {session['total_size']} bytes, Time: {transfer_time:.2f}s")
            
            return {'success': True, 'file_path': output_path}
            
        except Exception as e:
            logger.error(f"Error finalizing session {session_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    def _handle_status(self, query_string):
        """Get session status"""
        try:
            params = parse_qs(query_string)
            session_id = params.get('s', [''])[0]
            
            if not session_id:
                self._send_error_response(400, "Missing session_id")
                return
            
            with self.session_lock:
                if session_id not in self.sessions:
                    self._send_error_response(404, "Session not found")
                    return
                
                session = self.sessions[session_id]
                progress = len(session['received_chunks']) / session['total_chunks'] * 100
                
                response = {
                    'session_id': session_id,
                    'status': session['status'],
                    'progress': progress,
                    'received_chunks': len(session['received_chunks']),
                    'total_chunks': session['total_chunks'],
                    'filename': session['filename']
                }
                
                if session['status'] == 'completed':
                    response['file_path'] = session.get('file_path', '')
                    response['transfer_time'] = session.get('end_time', 0) - session['start_time']
                
                self._send_json_response(200, response)
                
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            self._send_error_response(500, f"Failed to get status: {str(e)}")
    
    def _send_json_response(self, status_code, data):
        """Send JSON response"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Connection', 'close')  # Close connection to prevent issues
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
    
    def _send_error_response(self, status_code, message):
        """Send error response"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Connection', 'close')  # Close connection to prevent issues
        self.end_headers()
        error_data = {'error': message, 'status_code': status_code}
        self.wfile.write(json.dumps(error_data).encode('utf-8'))

def cleanup_sessions():
    """Clean up old sessions"""
    with DFPHandler.session_lock:
        current_time = time.time()
        expired_sessions = []
        
        for session_id, session in DFPHandler.sessions.items():
            # Remove sessions older than 1 hour
            if current_time - session.get('last_activity', 0) > 3600:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            session = DFPHandler.sessions[session_id]
            try:
                if os.path.exists(session['session_dir']):
                    shutil.rmtree(session['session_dir'])
            except Exception as e:
                logger.warning(f"Failed to clean up session {session_id}: {e}")
            
            del DFPHandler.sessions[session_id]
            logger.info(f"Cleaned up expired session: {session_id}")

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info("Shutting down server...")
    cleanup_sessions()
    sys.exit(0)

def run_server(host='localhost', port=8080, enable_encryption=False):
    """Run the file transfer server"""
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    server_address = (host, port)
    
    DFPHandler.cipher = DFPCipher()
    logger.debug(f"DFP Cipher Init Finish. Please Check Your Public Key: \n{DFPHandler.cipher.rsa_key.publickey().export_key().decode()}")
    DFPHandler.enable_encryption = enable_encryption
    httpd = HTTPServer(server_address, DFPHandler)
    
    logger.info(f"Starting file transfer server on {host}:{port}")
    logger.info("Available endpoints:")
    logger.info("  GET  /cs?f=X&s=Y&c=Z&h=H")
    logger.info("  POST /k (with JSON body)")
    logger.info("  POST /fs (with JSON body)")
    logger.info("  GET  /status?s=X")
    logger.info("Press Ctrl+C to stop the server")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
        cleanup_sessions()
        httpd.shutdown()


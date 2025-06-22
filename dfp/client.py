#!/usr/bin/env python3
"""
File Transfer Client disguised as HTTP client
Handles file uploads through HTTP requests with parallel processing
"""

import os
import json
import hashlib
import threading
import time
import random
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urljoin
import logging
import argparse

from .cipher import DFPCipher

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DFPClient:
    
    def __init__(
        self, 
        server_url,
        enable_encryption=False, 
        max_workers=5, 
        chunk_size=1024*1024,
        chunk_size_variance=0.5,
    ):
        """
        Initialize the DFP client
        
        Args:
            server_url (str): Base URL of the DFP server (e.g., 'http://localhost:8080')
            max_workers (int): Maximum number of parallel workers
            chunk_size (int): Base chunk size in bytes
            chunk_size_variance (float): Random change chunk size range
        """

        if enable_encryption:
            self.cipher = DFPCipher()
            logger.debug(f"DFP Cipher Init Finish. Please Check Your Public Key: \n{self.cipher.rsa_key.publickey().export_key().decode()}")
        else:
            self.cipher = None
        self.server_url = server_url.rstrip('/')
        self.max_workers = max_workers
        self.base_chunk_size = chunk_size
        self.chunk_size_variance = chunk_size_variance
        self.session = self._create_requests_session()
    
    def _create_requests_session(self):
        """Create a requests session with retry logic and connection pooling"""
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,  # Total number of retries
            backoff_factor=0.5,  # Wait 0.5, 1, 2 seconds between retries
            status_forcelist=[500, 502, 503, 504],  # Retry on these status codes
            allowed_methods=["GET", "POST"]  # Allow retries on GET and POST
        )
        
        # Configure adapter with connection pooling
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=self.max_workers * 2,  # Connection pool size
            pool_maxsize=self.max_workers * 2,  # Max connections in pool
            pool_block=False  # Don't block when pool is full
        )
        
        # Mount adapter for both HTTP and HTTPS
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Configure session headers for better performance
        session.headers.update({
            'User-Agent': 'DFPClient/1.0',
            'Connection': 'keep-alive',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        
        return session
    
    def send(self, file_path, progress_callback=None):
        """
        Transfer a file to the server with parallel processing
        
        Args:
            file_path (str): Path to the file to transfer
            progress_callback (callable): Optional callback for progress updates
            
        Returns:
            dict: Transfer result with status and details
        """
        try:
            if not os.path.exists(file_path):
                return {'success': False, 'error': f'File not found: {file_path}'}
            
            file_size = os.path.getsize(file_path)
            filename = os.path.basename(file_path)
            
            logger.info(f"Starting transfer of {filename} ({file_size} bytes)")
            
            # Calculate file hash
            file_hash = self._calculate_file_hash(file_path)
            
            # Create chunks with variable sizes
            chunks = self._create_chunks(file_path)
            total_chunks = len(chunks)
            
            logger.info(f"Created {total_chunks} chunks for transfer")
            
            # Step 1: Create session
            session_id = self._create_transfer_session(filename, file_size, total_chunks, file_hash)
            if not session_id:
                return {'success': False, 'error': 'Failed to create session'}
            
            logger.info(f"Created session: {session_id}")
            
            # Step 2: Upload chunks in parallel
            upload_result = self._upload_chunks_parallel(session_id, chunks, progress_callback)
            if not upload_result['success']:
                return upload_result
            
            # Step 3: Complete session
            complete_result = self._complete_session(session_id)
            if not complete_result['success']:
                return complete_result
            
            transfer_time = time.time() - upload_result['start_time']
            speed = file_size / transfer_time if transfer_time > 0 else 0
            
            logger.info(f"Completed successfully in {transfer_time:.2f}s "
                       f"({speed/1024/1024:.2f} MB/s)")
            
            return {
                'success': True,
                'session_id': session_id,
                'filename': filename,
                'file_size': file_size,
                'transfer_time': transfer_time,
                'speed_mbps': speed / 1024 / 1024,
                'chunks_uploaded': total_chunks
            }
            
        except Exception as e:
            logger.error(f"Transfer failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _calculate_file_hash(self, file_path):
        """Calculate MD5 hash of the file"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def _create_chunks(self, file_path):
        """
        Create chunks with variable sizes (base_size +/- 50%)
        
        Returns:
            list: List of (chunk_index, chunk_data) tuples
        """
        chunks = []
        chunk_index = 0
        
        with open(file_path, 'rb') as f:
            while True:
                # Calculate variable chunk size (±chunk_size_variance of base size)
                variation = random.uniform(1 - self.chunk_size_variance, 1 + self.chunk_size_variance)
                chunk_size = int(self.base_chunk_size * variation)
                
                chunk_data = f.read(chunk_size)
                if self.cipher is not None:
                    start_time = time.time()
                    logger.debug("Encrypting current chunk")
                    chunk_data = self.cipher.encrypt(chunk_data, parallel_size=os.cpu_count())
                    logger.debug(f"Chunk encrypted, took {time.time() - start_time}s")
                if not chunk_data:
                    break
                chunks.append((chunk_index, chunk_data))
                chunk_index += 1
        
        return chunks
    
    def _create_transfer_session(self, filename, total_size, total_chunks, file_hash):
        """Create a new transfer session"""
        try:
            url = urljoin(self.server_url, '/cs')
            if self.cipher is not None:
                filename = self.cipher.encrypt(filename, parallel_size=1)
                filename = base64.b64encode(filename).decode('utf-8')
            params = {
                'f': filename,
                's': total_size,
                'c': total_chunks,
                'h': file_hash
            }
            
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            return data.get('session_id')
            
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            return None
    
    def _upload_chunks_parallel(self, session_id, chunks, progress_callback=None):
        """Upload chunks in parallel with improved error handling"""
        try:
            start_time = time.time()
            uploaded_chunks = 0
            total_chunks = len(chunks)
            failed_chunks = []
            retry_chunks = []
            
            def upload_chunk(chunk_info):
                chunk_index, chunk_data = chunk_info
                return self._upload_single_chunk(session_id, chunk_index, chunk_data)
            
            # Upload chunks in parallel
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all chunk uploads
                future_to_chunk = {
                    executor.submit(upload_chunk, chunk): chunk 
                    for chunk in chunks
                }
                
                # Process completed uploads
                for future in as_completed(future_to_chunk):
                    chunk = future_to_chunk[future]
                    try:
                        result = future.result(timeout=60)
                        if result['success']:
                            uploaded_chunks += 1
                            if progress_callback:
                                progress = (uploaded_chunks / total_chunks) * 100
                                progress_callback(progress, uploaded_chunks, total_chunks)
                        else:
                            # Add to retry list instead of immediately failing
                            retry_chunks.append(chunk)
                            logger.warning(f"Failed to upload chunk {chunk[0]}: {result['error']}")
                    except Exception as e:
                        retry_chunks.append(chunk)
                        logger.error(f"Exception uploading chunk {chunk[0]}: {e}")
            
            # Retry failed chunks with exponential backoff
            if retry_chunks:
                logger.info(f"Retrying {len(retry_chunks)} failed chunks...")
                for attempt in range(3):  # Max 3 retry attempts
                    if not retry_chunks:
                        break
                    
                    time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                    logger.info(f"Retry attempt {attempt + 1} for {len(retry_chunks)} chunks")
                    
                    still_failed = []
                    with ThreadPoolExecutor(max_workers=max(1, self.max_workers // 2)) as executor:
                        future_to_chunk = {
                            executor.submit(upload_chunk, chunk): chunk 
                            for chunk in retry_chunks
                        }
                        
                        for future in as_completed(future_to_chunk):
                            chunk = future_to_chunk[future]
                            try:
                                result = future.result(timeout=60)
                                if result['success']:
                                    uploaded_chunks += 1
                                    if progress_callback:
                                        progress = (uploaded_chunks / total_chunks) * 100
                                        progress_callback(progress, uploaded_chunks, total_chunks)
                                else:
                                    still_failed.append(chunk)
                            except Exception as e:
                                still_failed.append(chunk)
                                logger.error(f"Retry failed for chunk {chunk[0]}: {e}")
                    
                    retry_chunks = still_failed
                
                # Any remaining failed chunks are permanently failed
                failed_chunks = retry_chunks
            
            if failed_chunks:
                return {
                    'success': False, 
                    'error': f'Failed to upload chunks after retries: {[c[0] for c in failed_chunks]}',
                    'start_time': start_time
                }
            
            return {
                'success': True,
                'uploaded_chunks': uploaded_chunks,
                'start_time': start_time
            }
            
        except Exception as e:
            logger.error(f"Parallel upload failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _upload_single_chunk(self, session_id, chunk_index, chunk_data):
        """Upload a single chunk with improved error handling"""
        try:
            url = urljoin(self.server_url, '/k')
            
            # encrypt
            # if self.cipher is not None:
            #     chunk_data = self.cipher.encrypt(chunk_data)
            # Encode chunk data as base64
            chunk_data_b64 = base64.b64encode(chunk_data).decode('utf-8')
            
            payload = {
                'session_id': session_id,
                'chunk_index': chunk_index,
                'chunk_data': chunk_data_b64
            }
            
            response = self.session.post(
                url, 
                json=payload, 
                timeout=30,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()
            
            return {'success': True}
            
        except requests.exceptions.ConnectionError as e:
            return {'success': False, 'error': f'Connection error: {str(e)}'}
        except requests.exceptions.Timeout as e:
            return {'success': False, 'error': f'Timeout error: {str(e)}'}
        except requests.exceptions.RequestException as e:
            return {'success': False, 'error': f'Request error: {str(e)}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _complete_session(self, session_id):
        """Complete the transfer session"""
        try:
            url = urljoin(self.server_url, '/fs')
            payload = {'session_id': session_id}
            
            response = self.session.post(
                url, 
                json=payload, 
                timeout=60,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()
            
            data = response.json()
            if data['status'] == 'completed':
                return {'success': True, 'file_path': data.get('fp')}
            else:
                return {'success': False}
            
        except Exception as e:
            logger.error(f"Failed to complete session: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_session_status(self, session_id):
        """Get the status of a transfer session"""
        try:
            url = urljoin(self.server_url, '/status')
            params = {'s': session_id}
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Failed to get session status: {e}")
            return None

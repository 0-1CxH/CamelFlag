#!/usr/bin/env python3
"""
Test script for the file transfer system
Creates a sample file and demonstrates the transfer process
"""

import os
import time
import tempfile
import hashlib
from dfp.client import DFPClient
import subprocess
import sys

def create_test_file(file_path, size_mb=10):
    """Create a test file with random data"""
    print(f"Creating test file: {file_path} ({size_mb}MB)")
    
    with open(file_path, 'wb') as f:
        # Write random data in chunks to avoid memory issues
        chunk_size = 1024 * 1024  # 1MB chunks
        remaining = size_mb * 1024 * 1024
        
        while remaining > 0:
            chunk = os.urandom(min(chunk_size, remaining))
            f.write(chunk)
            remaining -= len(chunk)
    
    # Calculate file hash
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    
    print(f"Test file created successfully")
    print(f"File size: {os.path.getsize(file_path)} bytes")
    print(f"File hash: {hash_md5.hexdigest()}")
    return hash_md5.hexdigest()

def verify_file(file_path, expected_hash):
    """Verify file integrity by comparing hashes"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    
    actual_hash = hash_md5.hexdigest()
    matches = actual_hash == expected_hash
    
    print(f"File verification: {'✅ PASS' if matches else '❌ FAIL'}")
    print(f"Expected hash: {expected_hash}")
    print(f"Actual hash:   {actual_hash}")
    
    return matches

def test_transfer(server_url='http://localhost:8080', file_size_mb=10, workers=10):
    """Test the file transfer system"""
    print("=" * 60)
    print("FILE TRANSFER SYSTEM TEST")
    print("=" * 60)
    
    # Create test file
    test_file = tempfile.NamedTemporaryFile(delete=False, suffix='.test')
    test_file.close()
    
    try:
        # Create test file with random data
        expected_hash = create_test_file(test_file.name, file_size_mb)
        
        print("\n" + "-" * 40)
        print("STARTING TRANSFER TEST")
        print("-" * 40)
        
        # Create client
        client = DFPClient(
            server_url=server_url,
            max_workers=workers,
            chunk_size=1024*1024  # 1MB chunks
        )
        
        # Transfer file
        start_time = time.time()
        result = client.send(test_file.name)
        end_time = time.time()
        
        print("\n" + "-" * 40)
        print("TRANSFER RESULTS")
        print("-" * 40)
        
        if result['success']:
            print("✅ Transfer completed successfully!")
            print(f"Session ID: {result['session_id']}")
            print(f"File: {result['filename']}")
            print(f"Size: {result['file_size']} bytes")
            print(f"Transfer time: {result['transfer_time']:.2f} seconds")
            print(f"Speed: {result['speed_mbps']:.2f} MB/s")
            print(f"Chunks uploaded: {result['chunks_uploaded']}")
            
            # Verify the transferred file
            transferred_file = result['filename']
            if os.path.exists(transferred_file):
                print(f"\nVerifying transferred file: {transferred_file}")
                if verify_file(transferred_file, expected_hash):
                    print("\n🎉 TEST PASSED: File transfer and verification successful!")
                    return True
                else:
                    print("\n❌ TEST FAILED: File verification failed!")
                    return False
            else:
                print(f"\n❌ TEST FAILED: Transferred file not found: {transferred_file}")
                return False
        else:
            print("❌ Transfer failed!")
            print(f"Error: {result['error']}")
            return False
            
    finally:
        # Clean up test file
        try:
            os.unlink(test_file.name)
        except:
            pass

def check_server_running(server_url):
    """Check if the server is running"""
    try:
        import requests
        response = requests.get(f"{server_url}/status?session_id=test", timeout=5)
        return True
    except:
        return False

def main():
    """Main test function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test File Transfer System')
    parser.add_argument('--server', default='http://localhost:8080', 
                       help='Server URL (default: http://localhost:8080)')
    parser.add_argument('--size', type=int, default=10, 
                       help='Test file size in MB (default: 10)')
    parser.add_argument('--workers', type=int, default=10, 
                       help='Number of parallel workers (default: 10)')
    parser.add_argument('--start-server', action='store_true',
                       help='Automatically start server if not running')
    
    args = parser.parse_args()
    
    # Check if server is running
    if not check_server_running(args.server):
        print(f"❌ Server not running at {args.server}")
        
        if args.start_server:
            print("Starting server...")
            try:
                # Start server in background
                server_process = subprocess.Popen([
                    sys.executable, 'server.py', 
                    '--host', 'localhost', 
                    '--port', '8080'
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                # Wait for server to start
                time.sleep(3)
                
                if server_process.poll() is None:
                    print("✅ Server started successfully")
                else:
                    print("❌ Failed to start server")
                    return 1
                    
            except Exception as e:
                print(f"❌ Error starting server: {e}")
                return 1
        else:
            print("Please start the server first:")
            print(f"  python server.py --host localhost --port 8080")
            return 1
    
    # Run test
    success = test_transfer(args.server, args.size, args.workers)
    
    if success:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print("\n❌ Tests failed!")
        return 1

if __name__ == '__main__':
    exit(main()) 
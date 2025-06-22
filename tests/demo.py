#!/usr/bin/env python3
"""
Demo script for the file transfer system
Shows how to use the system programmatically with different configurations
"""

import os
import time
import tempfile
from dfp.client import DFPClient

def demo_basic_transfer():
    """Demo basic file transfer"""
    print("=" * 50)
    print("DEMO: Basic File Transfer")
    print("=" * 50)
    
    # Create a test file
    test_file = tempfile.NamedTemporaryFile(delete=False, suffix='.demo')
    test_file.write(b"This is a test file for the file transfer demo.\n" * 1000)
    test_file.close()
    
    try:
        # Create client with default settings
        client = DFPClient(
            server_url='http://localhost:8080',
            max_workers=5,
            chunk_size=512*1024  # 512KB chunks
        )
        
        print(f"Transferring file: {test_file.name}")
        result = client.send(test_file.name)
        
        if result['success']:
            print("✅ Transfer successful!")
            print(f"Speed: {result['speed_mbps']:.2f} MB/s")
            print(f"Time: {result['transfer_time']:.2f}s")
        else:
            print(f"❌ Transfer failed: {result['error']}")
            
    finally:
        os.unlink(test_file.name)

def demo_high_performance_transfer():
    """Demo high-performance transfer with more workers"""
    print("\n" + "=" * 50)
    print("DEMO: High-Performance Transfer")
    print("=" * 50)
    
    # Create a larger test file
    test_file = tempfile.NamedTemporaryFile(delete=False, suffix='.demo')
    
    # Write 5MB of data
    for i in range(5000):
        test_file.write(f"Line {i}: This is test data for high-performance transfer demo.\n".encode())
    test_file.close()
    
    try:
        # Create client with high-performance settings
        client = DFPClient(
            server_url='http://localhost:8080',
            max_workers=20,  # More workers for better performance
            chunk_size=1024*1024  # 1MB chunks
        )
        
        print(f"Transferring file: {test_file.name}")
        print(f"File size: {os.path.getsize(test_file.name)} bytes")
        print(f"Workers: {client.max_workers}")
        print(f"Chunk size: {client.base_chunk_size} bytes")
        
        result = client.send(test_file.name)
        
        if result['success']:
            print("✅ High-performance transfer successful!")
            print(f"Speed: {result['speed_mbps']:.2f} MB/s")
            print(f"Time: {result['transfer_time']:.2f}s")
            print(f"Chunks: {result['chunks_uploaded']}")
        else:
            print(f"❌ Transfer failed: {result['error']}")
            
    finally:
        os.unlink(test_file.name)

def demo_progress_callback():
    """Demo transfer with progress callback"""
    print("\n" + "=" * 50)
    print("DEMO: Transfer with Progress Callback")
    print("=" * 50)
    
    # Create test file
    test_file = tempfile.NamedTemporaryFile(delete=False, suffix='.demo')
    test_file.write(b"Progress demo file content.\n" * 2000)
    test_file.close()
    
    def progress_callback(progress, uploaded, total):
        """Custom progress callback"""
        bar_length = 30
        filled_length = int(bar_length * progress / 100)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        print(f"\rProgress: [{bar}] {progress:.1f}% ({uploaded}/{total})", end='', flush=True)
    
    try:
        client = DFPClient(
            server_url='http://localhost:8080',
            max_workers=8,
            chunk_size=256*1024  # 256KB chunks for more progress updates
        )
        
        print(f"Transferring file: {test_file.name}")
        result = client.send(test_file.name, progress_callback)
        
        print()  # New line after progress bar
        
        if result['success']:
            print("✅ Transfer with progress tracking successful!")
            print(f"Speed: {result['speed_mbps']:.2f} MB/s")
        else:
            print(f"❌ Transfer failed: {result['error']}")
            
    finally:
        os.unlink(test_file.name)

def demo_session_status():
    """Demo checking session status"""
    print("\n" + "=" * 50)
    print("DEMO: Session Status Checking")
    print("=" * 50)
    
    # Create test file
    test_file = tempfile.NamedTemporaryFile(delete=False, suffix='.demo')
    test_file.write(b"Status demo file.\n" * 100)
    test_file.close()
    
    try:
        client = DFPClient(
            server_url='http://localhost:8080',
            max_workers=3,
            chunk_size=128*1024
        )
        
        print(f"Transferring file: {test_file.name}")
        result = client.send(test_file.name)
        
        if result['success']:
            session_id = result['session_id']
            print(f"✅ Transfer completed. Session ID: {session_id}")
            
            # Check session status
            print("\nChecking session status...")
            status = client.get_session_status(session_id)
            
            if status:
                print("Session Status:")
                print(f"  Status: {status['status']}")
                print(f"  Progress: {status['progress']:.1f}%")
                print(f"  Received chunks: {status['received_chunks']}/{status['total_chunks']}")
                print(f"  Filename: {status['filename']}")
                
                if status['status'] == 'completed':
                    print(f"  File path: {status.get('file_path', 'N/A')}")
                    print(f"  Transfer time: {status.get('transfer_time', 'N/A')}s")
            else:
                print("❌ Failed to get session status")
        else:
            print(f"❌ Transfer failed: {result['error']}")
            
    finally:
        os.unlink(test_file.name)

def main():
    """Run all demos"""
    print("File Transfer System - Demo Suite")
    print("Make sure the server is running: python server.py")
    print()
    
    # Check if server is running
    try:
        import requests
        response = requests.get('http://localhost:8080/status?session_id=test', timeout=5)
        print("✅ Server is running")
    except:
        print("❌ Server is not running. Please start it first:")
        print("  python server.py")
        return
    
    print()
    
    # Run demos
    try:
        demo_basic_transfer()
        time.sleep(1)
        
        demo_high_performance_transfer()
        time.sleep(1)
        
        demo_progress_callback()
        time.sleep(1)
        
        demo_session_status()
        
        print("\n" + "=" * 50)
        print("🎉 All demos completed successfully!")
        print("=" * 50)
        
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")

if __name__ == '__main__':
    main() 
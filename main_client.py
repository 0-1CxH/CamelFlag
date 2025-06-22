import argparse
from dfp.client import DFPClient

def progress_callback(progress, uploaded, total):
    """Default progress callback"""
    print(f"\rProgress: {progress:.2f}% ({uploaded}/{total} chunks)", end='', flush=True)


def main():
    """Main function for command-line usage"""
    parser = argparse.ArgumentParser(description='File Transfer Client')
    parser.add_argument('file_path', help='Path to the file to transfer')
    parser.add_argument('--server', default='http://localhost:8080', 
                       help='Server URL (default: http://localhost:8080)')
    parser.add_argument('--workers', type=int, default=8, 
                       help='Number of parallel workers (default: 1)')
    parser.add_argument('--chunk-size', type=int, default=4*1024*1024, 
                       help='Base chunk size in bytes (default: 4MB)')
    parser.add_argument('--status', help='Check status of existing session ID')
    parser.add_argument('--encrypt', action='store_true', help='Do encryption before sending chunks')
    
    args = parser.parse_args()
    
    client = DFPClient(
        server_url=args.server,
        max_workers=args.workers,
        chunk_size=args.chunk_size,
        enable_encryption=args.encrypt,
    )
    
    if args.status:
        # Check session status
        status = client.get_session_status(args.status)
        if status:
            print(json.dumps(status, indent=2))
        else:
            print("Failed to get session status")
    else:
        print(f"Sending: {args.file_path}")
        print(f"Server: {args.server}")
        print(f"Workers: {args.workers}")
        print(f"Chunk size: {args.chunk_size} bytes")
        print("-" * 50)
        
        result = client.send(args.file_path, progress_callback)
        
        print()  # New line after progress
        print("-" * 50)
        
        if result['success']:
            print("✅ Completed successfully!")
            print(f"Session ID: {result['session_id']}")
            print(f"File: {result['filename']}")
            print(f"Size: {result['file_size']} bytes")
            print(f"Time: {result['transfer_time']:.2f} seconds")
            print(f"Speed: {result['speed_mbps']:.5f} MB/s")
            print(f"Chunks: {result['chunks_uploaded']}")
        else:
            print("❌ Failed!")
            print(f"Error: {result['error']}")

if __name__ == '__main__':
    main() 
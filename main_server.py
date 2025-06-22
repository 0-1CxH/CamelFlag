from dfp.server import run_server

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='File Transfer Server')
    parser.add_argument('--host', default='localhost', help='Server host (default: localhost)')
    parser.add_argument('--port', type=int, default=8080, help='Server port (default: 8080)')
    
    args = parser.parse_args()
    print(f"DFP Server will be available at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop the server")
    run_server(args.host, args.port) 
Install Dependencies:

```
pip install -r requirements.txt
```


Run DFP Server:

```
python main_server.py --host HOST_ADDR --port HOST_PORT 
```

Run DFP Client:

```
python main_client.py FILE_PATH --server http://HOST_ADDR:HOST_PORT --workers 5 --chunk-size 4194304
```
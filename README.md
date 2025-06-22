Install Dependencies:

```
pip install -r requirements.txt
```


Run DFP Server:

```
python main_server.py --host HOST_ADDR --port HOST_PORT # --encrypt
```

Run DFP Client:

```
python main_client.py FILE_PATH --server http://HOST_ADDR:HOST_PORT --workers 5 --chunk-size 4194304 # --encrypt
```

Note:

`--encrypt` will be safer, but much slower; e.g. 6M file takes 16.52 s w/ encryption and 0.05s w/o encryption, larger file takes longer time on decryption
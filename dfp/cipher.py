from Crypto.PublicKey import RSA
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA256
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.Util import Counter
import multiprocessing as mp
from functools import partial
import os
import math

class DFPCipher:
    def __init__(self, passkey=None, salt=None) -> None:
        self.rsa_key = None
        self.passkey = input("ENTER YOUR PASSKEY:") if passkey is None else passkey
        self.salt = "dfp#2025" if salt is None else salt

        self.keygen()

    def keygen(self):
        # The same passkey and salt generate the same dk, which seeds the AES-CTR cipher. 
        # This guarantees reproducible random bytes.
        passkey = self.passkey
        salt = self.salt
        # Convert passkey to bytes if it's a string
        if isinstance(passkey, str):
            passkey_bytes = passkey.encode('utf-8')
        else:
            passkey_bytes = passkey
        
        # Derive a 32-byte key using PBKDF2 with 100,000 iterations
        dk = PBKDF2(passkey_bytes, salt, dkLen=32, count=100000, hmac_hash_module=SHA256)
        
        # Initialize AES-CTR as a deterministic PRNG
        ctr = Counter.new(128, initial_value=0)  # 128-bit counter starting at 0
        aes_cipher = AES.new(dk, AES.MODE_CTR, counter=ctr)
        
        # Deterministic random bytes generator
        def rand_func(n):
            return aes_cipher.encrypt(b'\x00' * n)  # Encrypt zeros to get keystream
        
        # Generate RSA key pair
        key = RSA.generate(2048, randfunc=rand_func)

        self.rsa_key = key
        return key
    
    @staticmethod
    def split_data(data, chunk_size):
        return [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]

    @staticmethod
    def encrypt_by_segment(plaintext, passkey, salt):
        assert isinstance(plaintext, bytes)
        cipher = DFPCipher(passkey, salt)
        rsa_key = cipher.keygen()
        pkcs = PKCS1_OAEP.new(rsa_key.publickey(), hashAlgo=SHA256)
        plaintext_segments = cipher.split_data(plaintext, 190)
        return b''.join([pkcs.encrypt(seg) for seg in plaintext_segments])
    
    @staticmethod
    def decrypt_by_segment(ciphertext, passkey, salt):
        assert isinstance(ciphertext, bytes)
        cipher = DFPCipher(passkey, salt)
        rsa_key = cipher.keygen()
        pkcs = PKCS1_OAEP.new(rsa_key, hashAlgo=SHA256)
        ciphertext_segments = cipher.split_data(ciphertext, 256)
        return b''.join([pkcs.decrypt(seg) for seg in ciphertext_segments])

    def encrypt(self, plaintext, parallel_size=8):
        """
        Encrypt plaintext using multiprocessing for faster performance.
        
        Args:
            plaintext: String or bytes to encrypt
            use_multiprocessing: Whether to use multiprocessing (default: True)
            num_processes: Number of processes to use (default: CPU count)
        """
        if self.rsa_key is None:
            raise ValueError("Must generate RSA key first")
        
        # Convert string to bytes if needed
        if isinstance(plaintext, str):
            plaintext_bytes = plaintext.encode('utf-8')
        elif isinstance(plaintext, bytes):
            plaintext_bytes = plaintext
        else:
            raise ValueError("Plaintext must be string or bytes")
        
        # Distribute bytes across ranks/processes
        byte_num_on_each_rank = math.ceil(len(plaintext_bytes) / float(parallel_size))
        bytes_on_ranks = [plaintext_bytes[rank*byte_num_on_each_rank: (rank+1)*byte_num_on_each_rank] for rank in range(parallel_size)]
        # Create partial function with fixed passkey and salt
        encrypt_func = partial(self.encrypt_by_segment, passkey=self.passkey, salt=self.salt)
        # Process segments in parallel
        with mp.Pool(processes=parallel_size) as pool:
            ciphertext_segments = pool.map(encrypt_func, bytes_on_ranks)
        
        ciphertext = b''.join(ciphertext_segments)
        
        return ciphertext

    def decrypt(self, ciphertext, parallel_size=8, decode=False):
        """
        Decrypt ciphertext using multiprocessing for faster performance.
        
        Args:
            ciphertext: Bytes to decrypt
            decode: Whether to decode result to string (default: False)
            use_multiprocessing: Whether to use multiprocessing (default: True)
            num_processes: Number of processes to use (default: CPU count)
        """
        if self.rsa_key is None:
            raise ValueError("Must generate RSA key first")
        
        assert isinstance(ciphertext, bytes)
        ciphertext_segments = self.split_data(ciphertext, 256)
        
        segment_num_on_each_rank = math.ceil(len(ciphertext_segments) / float(parallel_size))

        segments_on_ranks = [
             b''.join(ciphertext_segments[rank*segment_num_on_each_rank: (rank+1)*segment_num_on_each_rank])
             for rank in range(parallel_size)
        ]
        
        # Create partial function with fixed passkey and salt
        decrypt_func = partial(self.decrypt_by_segment, 
                                passkey=self.passkey, 
                                salt=self.salt)
        
        # Process segments in parallel
        with mp.Pool(processes=parallel_size) as pool:
            plaintext_segments = pool.map(decrypt_func, segments_on_ranks)
        
        plaintext = b''.join(plaintext_segments)
        
        if decode:
            return plaintext.decode('utf-8')
        else:
            return plaintext

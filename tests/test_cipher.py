from dfp.cipher import DFPCipher

import time
import random 

def test_enc():
    c1 = DFPCipher("pk", "st") 
    c2 = DFPCipher("pk", "st") 

    short_example = b'1' * 327
    long_example = bytes(random.getrandbits(8) for _ in range(10 * 1024 * 1024))

    ct = c1.encrypt(short_example)
    print(ct)
    pt = c2.decrypt(ct)
    print(pt)
    print(pt == short_example)

    for s in [8, 4, 2, 1]:
        print(f"Testing parallel size {s}")
        start_time = time.time()
        ct = c1.encrypt(long_example, s)
        print(f"Encryption took {time.time() - start_time}, Encrypted Size {len(ct)}")
        start_time = time.time()
        pt = c2.decrypt(ct, s)
        print(f"Decryption took {time.time() - start_time}")
        print(f"{pt==long_example}")

    
# 1MB 
# Testing parallel size 1
# Encryption took 4.33208703994751
# Decryption took 22.032608032226562
# True
# Testing parallel size 2
# Encryption took 2.780853033065796
# Decryption took 11.626352787017822
# True
# Testing parallel size 4
# Encryption took 2.035529851913452
# Decryption took 6.37539005279541
# True
# Testing parallel size 8
# Encryption took 1.842853307723999
# Decryption took 5.8313398361206055
# True

# 10MB
# Testing parallel size 8
# Encryption took 10.425027132034302, Encrypted Size 14129152
# Decryption took 48.16127300262451
# Testing parallel size 4
# Encryption took 11.99404001235962, Encrypted Size 14129152
# Decryption took 65.35753083229065
# True
# Testing parallel size 2
# Encryption took 17.181864023208618, Encrypted Size 14128640
# Testing parallel size 1
# Encryption took 32.997472047805786

    

if __name__ == "__main__":
    test_enc()
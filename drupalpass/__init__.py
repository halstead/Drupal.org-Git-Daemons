import hashlib

# Calculate a non-truncated Drupal 7 compatible password hash.
# The consumer of these hashes must truncate correctly.

class DrupalHash:

    def __init__(self,stored_hash, password):
        self.itoa64 = './0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
        self.last_hash = self.rehash(stored_hash, password)
    
    def get_hash(self):
        return self.last_hash

    def password_get_count_log2(self, setting):
        return self.itoa64.index(setting[3])

    def password_crypt(self, algo, password, setting):
        setting = setting[0:12]
        if setting[0] != '$' or setting[2] != '$':
            return False

        count_log2 = self.password_get_count_log2(setting)
        salt = setting[4:12]
        if len(salt) < 8:
            return False
        count = 1 << count_log2

        if algo == 'md5':
            hash_func = hashlib.md5
        elif algo == 'sha512':
            hash_func = hashlib.sha512
        else:
            return False
        hash_str = hash_func(salt + password).digest()
        for c in range(count):
            hash_str = hash_func(hash_str + password).digest()
        output = setting + self.custom64(hash_str)
        return output

    def custom64(self, string, count = 0):
        if count == 0:
            count = len(string)
        output = ''
        i = 0
        itoa64 = self.itoa64
        while 1:
            value = ord(string[i])
            i += 1
            output += itoa64[value & 0x3f]
            if i < count:
                value |= ord(string[i]) << 8
            output += itoa64[(value >> 6) & 0x3f]
            if i >= count:
                break
            i += 1
            if i < count:
                value |= ord(string[i]) << 16
            output += itoa64[(value >> 12) & 0x3f]
            if i >= count:
                break
            i += 1
            output += itoa64[(value >> 18) & 0x3f]
            if i >= count:
               break
        return output

    def rehash(self, stored_hash, password):
        hash_length = len(stored_hash)
        # Plain Drupal 6 compatibility
        if hash_length == 32 and stored_hash.find('$') == -1:
            return hashlib.md5(password).hexdigest()
        # Drupal 7 and phpass compatible passwords
        if stored_hash[0:2] == 'U$':
            # Old password wrapped for compatibily 
            hash_prefix = 'U'
            stored_hash = stored_hash[1:]
            password = hashlib.md5(password).hexdigest()
        else:
            # Password has been reset since phpass support was added
            hash_prefix = ''
        hash_type = stored_hash[0:3]
        if hash_type == '$S$':
            hash_str = self.password_crypt('sha512', password, stored_hash)
        elif hash_type == '$H$' or hash_type == '$P$':
            hash_str = self.password_crypt('md5', password, stored_hash)
        else:
            # We don't know how to deal with this hash type
            return False
        hash_str = hash_prefix + hash_str
        # Only return the length that Drupal has stored
        return hash_str[:hash_length]

if __name__ == "__main__":
    ha = '$S$D5z1Wm4bevjS5EQ3OdB.lI0NFTnCyIuD6VFHs5fkdjFHo0lvsdmv'
    pw = 'admin'
    new_ha = DrupalHash(ha, pw)
    print "Original hash: %s" % ha
    print "Password hash: %s" % new_ha.get_hash()

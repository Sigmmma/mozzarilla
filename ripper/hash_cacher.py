from os.path import dirname
from time import time
from string import digits, ascii_letters
from traceback import format_exc

from reclaimer.hek.handler import HaloHandler
from binilla.handler import Handler
from supyr_struct.tag import Tag


valid_path_chars = " ()-_%s%s" % (digits, ascii_letters)

def bytes_to_hex(taghash):
    hsh = hex(int.from_bytes(taghash, 'big'))[2:]
    return '0x' + '0'*(len(taghash)*2-len(hsh)) + hsh


def clear_meta_only_fields(tagdata, def_id):
    if def_id == 'effe':
        # mask away the meta-only flags
        tagdata.flags.data &= 3
    elif def_id == 'pphy':
        tagdata.wind_coefficient = 0
        tagdata.wind_sine_modifier = 0
        tagdata.z_translation_rate = 0


class HashCacher(Handler):
    default_defs_path = "mozzarilla.ripper.defs"
    tag_lib = None
    stop_hashing = False
    
    #initialize the class
    def __init__(self, **kwargs):
        Handler.__init__(self, **kwargs)
        self.tagsdir = dirname(__file__) + "\\hash_caches\\"

        self.hashsize = 16
        self.hashmethod = 'md5'
        self.main_hashmap = {}

    def build_hashcache(self, cache_name, description):
        start = time()
        if self.tag_lib is None:
            raise TypeError("tag_lib not set. Cannot load tags for hashing.")
        tag_lib = self.tag_lib
        tagsdir = tag_lib.tagsdir

        print('Attempting to load existing hashcache...')
        # its faster to try and just update the hashcache if it already exists
        try:
            cache = self.build_tag(
                filepath=self.tagsdir + cache_name + ".hashcache")
            hashmap = self.hashcache_to_hashmap(cache)
            description = description.rstrip('\n')
            if len(description):
                cache.data.cache_description = description
            print("Existing hashcache loaded.\n"+
                  "    Contains %s hashes" % len(hashmap))
        except Exception:
            cache = None
            hashmap = {}
            print("Failed to locate and/or load an existing hashcache.\n"+
                  "    Creating a hashcache from scratch instead.")

        if self.stop_hashing:
            print('Hashing cancelled.')
            self.stop_hashing = False
            return
        
        print('Indexing...')
        
        tag_lib.index_tags()
        
        try:
            tagsdir = tag_lib.tagsdir
            tags    = tag_lib.tags

            print('\nFound %s tags of these %s types' % (
                tag_lib.tags_indexed, len(tags)))
            print('%s' % list(sorted(tags.keys())))

            initial_cache_filenames = set(hashmap.values())
            initial_cache_hashes = set(hashmap.keys())
            get_nodes = self.tag_lib.get_nodes_by_paths

            calculated_hashes = {}
            
            for def_id in sorted(tags):
                tag_coll = tags[def_id]

                if self.stop_hashing:
                    print('Hashing cancelled.')
                    self.stop_hashing = False
                    return

                print("Hashing %s '%s' tags..." % (len(tag_coll), def_id))
                
                for filepath in sorted(tag_coll):
                    if self.stop_hashing:
                        print('Hashing cancelled.')
                        self.stop_hashing = False
                        return

                    if filepath in initial_cache_filenames:
                        continue
                    try:
                        print("    %s" % filepath)

                        data = tag_lib.build_tag(
                            filepath=tagsdir + filepath).data

                        if self.stop_hashing:
                            print('Hashing cancelled.')
                            self.stop_hashing = False
                            return

                        '''need to do some extra stuff for certain
                        tags with fields that are normally zeroed
                        out as tags, but arent as meta.'''
                        clear_meta_only_fields(data.tagdata, def_id)

                        tag_lib.get_tag_hash(data[1], def_id, filepath,
                                             calculated_hashes)

                        taghash = calculated_hashes[filepath]

                        if taghash is None:
                            print("        ERROR: Above tag couldnt be hashed.")
                            continue
                        elif taghash in initial_cache_hashes:
                            continue
                        
                        if taghash in hashmap:
                            print(("        COLLISION: hash already exists\n" +
                                   "            hash:%s\n" +
                                   "            existing tag: '%s'\n")
                                  % (bytes_to_hex(taghash), hashmap[taghash]))
                        else:
                            hashmap[taghash] = filepath
                            
                        #delete the tag and hash buffer to help conserve ram
                        del tag_coll[filepath]
                    except Exception:
                        print(format_exc())

            if self.stop_hashing:
                print('Hashing cancelled.')
                self.stop_hashing = False
                return

            if cache is None:
                print('Building hashcache...')
                cache = self.hashmap_to_hashcache(hashmap, cache_name,
                                                  description)

            if self.stop_hashing:
                print('Hashing cancelled.')
                self.stop_hashing = False
                return

            print('Writing hashcache...')
            cache.serialize(temp=False, backup=False, int_test=False)
        except:
            print(format_exc())
        print('Hashing completed. Took %s seconds' % (time() - start))
        return cache

    def add_tag_to_hashmap(self, filepath, hashmap):
        tag_lib = self.tag_lib
        
        tag  = tag_lib.build_tag(filepath=tag_lib.tagsdir + filepath)
        data = tag.data
        def_id = tag.def_id      

        hash_buffer = tag_lib.get_tag_hash(data,
                                           tag_lib.tag_ref_cache[def_id],
                                           tag_lib.reflexive_cache[def_id],
                                           tag_lib.raw_data_cache[def_id])
        taghash = hash_buffer.digest()
        #hash buffer to help conserve ram
        del hash_buffer
        
        if taghash in hashmap:
            print(("WARNING: hash already exists\n"+
                   "    hash:%s\n"+
                   "    path(existing): '%s'\n"+
                   "    path(colliding):'%s'\n")
                  % (bytes_to_hex(taghash), hashmap[taghash], filepath))
        else:
            hashmap[taghash] = filepath

        return taghash


    def hashmap_to_hashcache(self, hashmap, cache_name="untitled",
                             cache_description='<no description>'):
        cache = self.build_tag(def_id='hashcache')
        
        cache.data.header.hashsize   = self.hashsize
        cache.data.header.hashmethod = self.hashmethod
        cache.data.cache_name        = str(cache_name)
        cache.data.cache_description = str(cache_description)

        cache_name = ''.join(c for c in cache_name if c in valid_path_chars)
        if not cache_name:
            cache_name = "untitled"
        cache.filepath = self.tagsdir + cache_name + ".hashcache"
        
        cache_array = cache.data.cache
        cache_array.extend(len(hashmap))
        
        i = 0
        for taghash in sorted(hashmap):
            cache_array[i].hash  = taghash
            cache_array[i].value = hashmap[taghash]
            i += 1

        return cache


    def hashcache_to_hashmap(self, hashcache):
        hashmap = {}
        cache_array = hashcache.data.cache
        for mapping in cache_array:
            hashmap[mapping.hash] = mapping.value

        return hashmap


    def load_all_hashmaps(self):
        self.index_tags()
        self.load_tags()
        
        for hashcache in self.tags['hashcache'].values():
            self.update_hashmap(hashcache)


    def update_hashmap(self, new_hashes, hashmap=None, overwrite=False):
        if hashmap is None:
            hashmap = self.main_hashmap
            
        if isinstance(new_hashes, dict):
            if overwrite:
                hashmap.update(new_hashes)
                return
            
            for taghash in new_hashes:
                if taghash not in hashmap:
                    hashmap[taghash] = new_hashes[taghash]
                    
        elif isinstance(new_hashes, Tag):
            new_hashes = new_hashes.data.cache
            
            if overwrite:
                for mapping in new_hashes:
                    hashmap[mapping.hash] = mapping.value
                return
            
            for mapping in new_hashes:
                taghash = mapping.hash
                
                if taghash not in hashmap:
                    hashmap[taghash] = mapping.value

import zlib

from os.path import dirname, join
from struct import unpack
from tkinter.filedialog import askopenfilenames

from supyr_struct.defs.util import sanitize_path
from supyr_struct.defs.constants import PATHDIV
from supyr_struct.defs.bitmaps.dds import dds_def


def bitmap_from_dds(app, fps=()):
    load_dir = app.bitmap_load_dir
    data_dir = app.data_dir
    if not data_dir:
        data_dir = ""
    if not load_dir:
        load_dir = data_dir
    
    if not fps:
        fps = askopenfilenames(
            initialdir=load_dir, parent=app,
            filetypes=(("DDS image", "*.dds"), ("All", "*")),
            title="Select dds files to turn into bitmap tags")

    if not fps:
        return

    for fp in fps:
        try:
            fp = sanitize_path(fp)
            app.bitmap_load_dir = dirname(fp)
            print("Creating bitmap from this dds texture:")
            print("    %s" % fp)

            dds_tag = dds_def.build(filepath=fp)
            dds_head = dds_tag.data.header
            caps  = dds_head.caps
            caps2 = dds_head.caps2
            pixelformat = dds_head.dds_pixelformat
            pf_flags = pixelformat.flags
            dds_pixels = dds_tag.data.pixel_data
            if caps2.cubemap and not(caps2.pos_x and caps2.neg_x and
                                     caps2.pos_y and caps2.neg_y and
                                     caps2.pos_z and caps2.neg_z):
                raise TypeError(
                    "    DDS image is malformed and does not " +
                    "    contain all six necessary cubemap faces.")
                
            elif not dds_head.flags.pixelformat:
                raise TypeError(
                    "    DDS image is malformed and does not " +
                    "    contain a pixelformat structure.")
        except Exception:
            print("    Could not load dds image")
            return

        # make the tag window
        window = app.load_tags(filepaths='', def_id='bitm')
        if not window:
            return
        window = window[0]

        # get the bitmap tag and make a new bitmap block
        window.update_title(fp.split(PATHDIV)[-1])
        bitm_tag = window.tag
        bitm_data = bitm_tag.data.tagdata
        bitm_data.bitmaps.STEPTREE.append()
        bitm_block = bitm_data.bitmaps.STEPTREE[-1]
        bitm_block.bitm_id.set_to("bitm")

        # get the dimensions
        width = dds_head.width
        height = dds_head.height
        depth = dds_head.depth
        if not caps2.volume:
            depth = 1

        # set up the dimensions
        bitm_block.width = width
        bitm_block.height = height
        bitm_block.depth = depth

        # set the mipmap count
        if dds_head.caps.mipmaps:
            bitm_block.mipmaps = max(dds_head.mipmap_count-1, 0)

        # set up the flags
        fcc = pixelformat.four_cc.enum_name
        min_w = min_h = min_d = 1
        if fcc in ("DXT1", "DXT2", "DXT3", "DXT4", "DXT5"):
            bitm_block.flags.compressed = True
            min_w = min_h = 4
        bitm_block.flags.power_of_2_dim = True  # even if it isn't actually a
        # power of 2 texture, this flag need to be checked or tool will bitch

        bitm_block.format.data = -1
        bpp = 8  # bits per pixel

        # choose bitmap format
        if fcc == "DXT1":
            bitm_data.format.data = 0
            bitm_block.format.set_to("dxt1")
            bpp = 4
        elif fcc in ("DXT2", "DXT3"):
            bitm_data.format.data = 1
            bitm_block.format.set_to("dxt3")
        elif fcc in ("DXT4", "DXT5"):
            bitm_data.format.data = 2
            bitm_block.format.set_to("dxt5")
        elif pf_flags.rgb_space:
            bitcount = pixelformat.rgb_bitcount
            bitm_data.format.data = 4
            bpp = 32
            if pf_flags.has_alpha and bitcount == 32:
                bitm_block.format.set_to("a8r8g8b8")
            elif bitcount == 32:
                bitm_block.format.set_to("x8r8g8b8")
            elif bitcount in (15, 16):
                bpp = 16
                bitm_data.format.data = 3
                a_mask = pixelformat.a_bitmask
                r_mask = pixelformat.r_bitmask
                g_mask = pixelformat.g_bitmask
                b_mask = pixelformat.b_bitmask
                # shift the masks right until they're all the same scale
                while a_mask and not(a_mask&1): a_mask = a_mask >> 1
                while r_mask and not(r_mask&1): r_mask = r_mask >> 1
                while g_mask and not(g_mask&1): g_mask = g_mask >> 1
                while b_mask and not(b_mask&1): b_mask = b_mask >> 1

                mask_set = set((a_mask, r_mask, g_mask, b_mask))
                if mask_set == set((31, 63, 0)):
                    bitm_block.format.set_to("r5g6b5")
                elif mask_set == set((1, 31)):
                    bitm_block.format.set_to("a1r5g5b5")
                elif mask_set == set((15, )):
                    bitm_block.format.set_to("a4r4g4b4")

        elif pf_flags.alpha_only:
            bitm_block.format.set_to("a8")

        elif pf_flags.luminance:
            if pf_flags.has_alpha:
                bitm_block.format.set_to("a8y8")
            else:
                bitm_block.format.set_to("y8")

        if bitm_block.format.data == -1:
            bitm_block.format.data = bpp = 0
            print("    Unknown dds image format.")

        # make sure the number of mipmaps is accurate
        face_count = 6 if caps2.cubemap else 1
        w, h, d = width, height, depth
        pixel_counts = []

        # make a list of all the pixel counts of all the mipmaps.
        for mip in range(bitm_block.mipmaps):
            pixel_counts.append(w*h*d)
            w, h, d = (max(w//2, min_w),
                       max(h//2, min_h),
                       max(d//2, min_d))

        # see how many mipmaps can fit in the number of pixels in the dds file.
        while True:
            if (sum(pixel_counts)*bpp*face_count)//8 <= len(dds_pixels):
                break

            pixel_counts.pop(-1)

            #the mipmap count is zero and the bitmap still will
            #not fit within the space provided. Something's wrong
            if len(pixel_counts) == 0:
                print("    Size of the pixel data is too small to read even " +
                      "    the fullsize image from. This dds file is malformed.")
                break

        if len(pixel_counts) != bitm_block.mipmaps:
            print("    Mipmap count is too high for the number of pixels stored " +
                  "    in the dds file. The mipmap count has been reduced from " +
                  "    %s to %s." % (bitm_block.mipmaps, len(pixel_counts)))

        bitm_block.mipmaps = len(pixel_counts)

        # choose the texture type
        pixels = dds_pixels
        if caps2.volume:
            bitm_data.type.data = 1
            bitm_block.type.set_to("texture_3d")
        elif caps2.cubemap:
            # gotta rearrange the mipmaps and cubemap faces
            pixels = b''
            mip_count = bitm_block.mipmaps + 1
            images = [None]*6*(mip_count)
            pos = 0

            # dds images store all mips for one face next to each
            # other, and then the next set of mips for the next face.
            for face in range(6):
                w, h, d = width, height, depth
                for mip in range(mip_count):
                    i = mip*6 + face

                    # TODO: Fix this to determine the pixel data size
                    # using arbytmap's size calculation functions
                    image_size = (bpp*w*h*d)//8
                    images[i] = dds_pixels[pos: pos + image_size]

                    w, h, d = (max(w//2, min_w),
                               max(h//2, min_h),
                               max(d//2, min_d))
                    pos += image_size

            for image in images:
                pixels += image

            bitm_data.type.data = 2
            bitm_block.type.set_to("cubemap")

        # place the pixels from the dds tag into the bitmap tag
        bitm_data.processed_pixel_data.data = pixels
        
        # reload the window to display the newly entered info
        window.reload()
        # prompt the user to save the tag somewhere
        app.save_tag_as()


def bitmap_from_bitmap_source(app, e=None):
    load_dir = app.bitmap_load_dir
    if not load_dir:
        load_dir = app.last_load_dir
    
    fps = askopenfilenames(initialdir=load_dir, parent=app,
                           filetypes=(("bitmap", "*.bitmap"), ("All", "*")),
                           title="Select a bitmap tag to get the source tiff")

    if not fps:
        return

    app.bitmap_load_dir = dirname(fps[0])

    print('Creating bitmap from uncompressed source image of these bitmaps:')
    for fp in fps:
        fp = sanitize_path(fp)
        print("  %s" % fp)

        try:
            with open(fp, 'rb') as f:
                tag_data = f.read()

            tag_id = tag_data[36:40]
            engine_id = tag_data[60:64]
            
            # make sure this is a bitmap tag
            if tag_id == b'bitm' and engine_id == b'blam':
                # halo 1
                dims_off = 64+24
                size_off = 64+28
                data_off = 64+108
                end = ">"
            elif tag_id == b'mtib' and engine_id == b'!MLB':
                # halo 2
                dims_off = 64+16+24
                size_off = 64+16+28
                data_off = 64+16
                # get the size of the bitmap body from the tbfd structure
                data_off += unpack("<i", tag_data[data_off-4: data_off])[0]
                end = "<"
            else:
                print('    This file doesnt appear to be a bitmap tag.')
                continue

            width, height = unpack(end + "HH", tag_data[dims_off: dims_off+4])
            comp_size = unpack(end + "i", tag_data[size_off: size_off+4])[0]
        except Exception:
            print('    Could not load bitmap tag.')
            continue

        comp_data = tag_data[data_off: data_off + comp_size]

        if not comp_data:
            print('    No source image to extract.')
            continue

        try:
            data_size = unpack(end + "I", comp_data[:4])[0]
            if not data_size:
                print('    Source data is blank.')
                continue

            pixels = bytearray(zlib.decompress(comp_data[4:]))
        except Exception:
            print('    Could not decompress data.')
            continue

        # make the tag window
        try:
            window = app.load_tags(filepaths='', def_id='bitm')
        except LookupError:
            print('    Could not make a new bitmap. Change the tag set.')
        if not window:
            continue
        window = window[0]

        # get the bitmap tag and make a new bitmap block
        new_bitm_tag = window.tag
        new_bitm_data = new_bitm_tag.data.tagdata
        new_bitm_data.bitmaps.STEPTREE.append()
        bitm_block = new_bitm_data.bitmaps.STEPTREE[-1]

        # set up the id, dimensions, format, flags, mipmaps, and reg_points
        bitm_block.bitm_id.set_to("bitm")
        bitm_block.width = width
        bitm_block.height = height
        bitm_block.depth = 1
        bitm_block.format.set_to("a8r8g8b8")
        bitm_block.flags.power_of_2_dim = True
        bitm_block.registration_point_x = width // 2
        bitm_block.registration_point_y = height // 2

        # place the pixels into the bitmap tag
        new_bitm_data.processed_pixel_data.data = pixels
        new_bitm_tag.tags_dir = app.tags_dir
        new_bitm_tag.rel_filepath = "untitled%s.bitmap" % app.untitled_num
        new_bitm_tag.filepath = join(app.tags_dir + new_bitm_tag.rel_filepath)

        app.update_tag_window_title(window)

        # reload the window to display the newly entered info
        window.reload()
        # prompt the user to save the tag somewhere
        app.save_tag_as()

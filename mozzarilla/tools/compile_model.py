import os
import zlib

from os.path import dirname, join, relpath, basename, isfile, exists
from tkinter.filedialog import askdirectory

from supyr_struct.defs.util import sanitize_path, is_in_dir
from reclaimer.jms import read_jms
from reclaimer.hek.defs.objs.matrices import quaternion_to_matrix, Matrix


def model_from_jms(app, fps=(), tag_path=""):
    load_dir = app.jms_load_dir
    tags_dir = app.tags_dir
    data_dir = app.data_dir
    if not tags_dir:
        tags_dir = ""
    if not data_dir:
        data_dir = ""

    if not load_dir:
        load_dir = data_dir

    if not fps or not tag_path:
        src_dir = askdirectory(
            initialdir=load_dir, parent=app,
            title="Select folder containing the 'models' folder to compile")

        src_dir = sanitize_path(src_dir)
        models_dir = join(src_dir, "models", "")
        if not src_dir:
            return
        elif not exists(models_dir):
            print("The selected folder does not contain a 'models' folder.")
            return
        elif not is_in_dir(src_dir, data_dir):
            print("The selected folder is not in the data directory.")
            return

        fps = []
        tag_path = join(src_dir, basename(src_dir) + ".gbxmodel")
        tag_path = join(tags_dir, relpath(tag_path, data_dir))
        for _, __, files in os.walk(models_dir):
            for fname in files:
                if fname.lower().endswith(".jms"):
                    fps.append(join(models_dir, fname))

            break


    if not fps:
        print("    No valid jms files found in the folder.")
        return


    jms_datas = {}
    print("    Parsing jms files...")
    if app: app.update()
    for fp in fps:
        try:
            print("      %s" % fp)
            if app: app.update()
            with open(fp, "r") as f:
                jms_datas[fp] = read_jms(f.read())
        except Exception:
            print("        Could not parse jms file.")
            if app: app.update()

    if not jms_datas:
        return


    print("    Verifying integrity of jms files...")
    first_crc = None
    first_nodes = None
    crc_error = False
    error = False
    for fp in sorted(jms_datas):
        if app: app.update()
        crc, mats, regions, nodes, markers, verts, tris = jms_datas[fp]
        node_error = False
        if first_nodes is None:
            first_crc = crc
            first_nodes = nodes

        if len(nodes) != len(first_nodes):
            node_error = True
            nodes = ()
        elif first_crc != crc:
            crc_error = True

        node_ct = len(nodes)
        vert_ct = len(verts)
        region_ct = len(regions)
        mat_ct = len(mats)

        if node_ct >= 64:
            print("      Too many nodes. Max node count is 64.")
            node_error = True
            nodes = ()

        for i in range(node_ct):
            fn = first_nodes[i]
            n = nodes[i]
            if fn.name != n.name:
                print(("      Names of nodes '%s' do not match:\n"
                       "        '%s' and '%s'") % (i, fn.name, n.name))
            elif fn.first_child != n.first_child:
                print("      First children of node '%s' do not match." % n.name)
            elif fn.sibling_index != n.sibling_index:
                print("      Sibling index of node '%s' do not match." % n.name)
            elif (abs(fn.rot_i - n.rot_i) > 0.00001 or
                  abs(fn.rot_j - n.rot_j) > 0.00001 or
                  abs(fn.rot_k - n.rot_k) > 0.00001 or
                  abs(fn.rot_w - n.rot_w) > 0.00001):
                print("      Rotations of node '%s' do not match." % n.name)
            elif (abs(fn.pos_x - n.pos_x) > 0.000001 or
                  abs(fn.pos_y - n.pos_y) > 0.000001 or
                  abs(fn.pos_z - n.pos_z) > 0.000001):
                print("      Positions of node '%s' do not match." % n.name)
            elif first_nodes is not nodes:
                # only need to check the validity of the first jms's nodes
                continue
            elif (n.first_child >= len(nodes)):
                print("      First child of '%s' is invalid." % n.name)
            elif (n.sibling_index >= len(nodes)):
                print("      Sibling node of '%s' is invalid." % n.name)
            else:
                # nodes match
                continue

            node_error = True

        if node_error:
            error = True
            print("        Nodes do not match in:\n" +
                  "          %s" % fp)
            continue

        err_str = "        Invalid %s index in %s(s) in:\n          " + fp
        for tri in tris:
            if tri.v0 >= vert_ct or tri.v1 >= vert_ct or tri.v2 >= vert_ct:
                error = True
                print(err_str % ("vertex", "triangle"))
                break
            elif tri.region >= region_ct:
                error = True
                print(err_str % ("region", "triangle"))
                break
            elif tri.shader >= mat_ct:
                error = True
                print(err_str % ("shader", "triangle"))
                break

        for marker in markers:
            if marker.parent >= node_ct:
                error = True
                print(err_str % ("parent", "marker"))
                break
            elif marker.region >= region_ct:
                error = True
                print(err_str % ("region", "marker"))
                break

        for vert in verts:
            if vert.node_0 >= node_ct:
                error = True
                print(err_str % ("node_0", "vertex"))
                break
            elif vert.node_1 >= node_ct:
                error = True
                print(err_str % ("node_1", "vertex"))
                break

    if error:
        print("    Cannot compile model.")
        return
    elif crc_error:
        print("    Warning, not all node list checksums match.")


    updating = isfile(tag_path)
    if updating:
        print("    Updating existing gbxmodel tag.")
        tag_load_path = (tag_path, )
    else:
        print("    Creating new gbxmodel tag.")
        tag_load_path = ""

    if app: app.update()


    # make the tag window
    window = app.load_tags(filepaths=tag_load_path, def_id='mod2')
    if not window:
        return

    window = window[0]
    mod2_tag = window.tag

    window.is_new_tag = False
    mod2_tag.filepath = tag_path
    mod2_tag.rel_filepath = relpath(tag_path, tags_dir)

    tagdata = mod2_tag.data.tagdata




    mod2_tag.calc_internal_data()

    # reload the window to display the newly entered info
    window.reload()
    app.update_tag_window_title(window)
    #app.save_tag()

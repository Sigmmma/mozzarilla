import zlib

from os.path import dirname, join, relpath, basename, isfile
from tkinter.filedialog import askopenfilename
from traceback import format_exc

from reclaimer.model.jms import read_jms
from reclaimer.hek.defs.objs.matrices import quaternion_to_matrix, Matrix
from supyr_struct.defs.util import sanitize_path
from supyr_struct.defs.constants import PATHDIV


def physics_from_jms(app, fp=None):
    load_dir = app.jms_load_dir
    tags_dir = app.tags_dir
    data_dir = app.data_dir
    if not tags_dir:
        tags_dir = ""
    if not data_dir:
        data_dir = ""

    if not load_dir:
        load_dir = data_dir

    if not fp:
        fp = askopenfilename(
            initialdir=load_dir, parent=app,
            filetypes=(("JMS model", "*.jms"), ("All", "*")),
            title="Select jms file to turn into a physics tag")

    if not fp:
        return

    try:
        fp = sanitize_path(fp)
        app.jms_load_dir = dirname(fp)

        print("Creating physics from this jms file:")
        print("    %s" % fp)
        with open(fp, "r") as f:
            jms_model = read_jms(f.read(), "regions")

        markers = jms_model.markers
    except Exception:
        print(format_exc())
        print("    Could not load jms file")
        return

    tag_path = dirname(dirname(relpath(fp, data_dir)))
    rel_tagpath = join(tag_path, "%s.physics" % basename(tag_path))
    if not tag_path.startswith(".."):
        tag_path = join(tags_dir, rel_tagpath)
    else:
        tag_path = ""

    updating = False
    if isfile(tag_path):
        print("    Updating existing physics tag.")
        tag_load_path = (tag_path, )
        updating = True
    else:
        print("    Creating new physics tag.")
        tag_load_path = ""

    # make the tag window
    window = app.load_tags(filepaths=tag_load_path, def_id='phys')
    if not window:
        return
    window = window[0]
    phys_tag = window.tag

    window.is_new_tag = False
    phys_tag.filepath = tag_path
    phys_tag.rel_filepath = rel_tagpath

    tagdata = phys_tag.data.tagdata
    mass_points = tagdata.mass_points.STEPTREE

    if not updating:
        # making fresh physics tag. use default values
        tagdata.radius = -1.0
        tagdata.moment_scale = 0.3
        tagdata.mass = 1.0
        tagdata.density = 1.0
        tagdata.gravity_scale = 1.0
        tagdata.ground_friction = 0.2
        tagdata.ground_depth = 0.2
        tagdata.ground_damp_fraction = 0.05
        tagdata.ground_normal_k1 = 0.7071068
        tagdata.ground_normal_k0 = 0.5
        tagdata.water_friction = 0.05
        tagdata.water_depth = 0.25
        tagdata.water_density = 1.0
        tagdata.air_friction = 0.001

    existing_mp_names = {}
    for i in range(len(mass_points)):
        existing_mp_names[mass_points[i].name.lower()] = i

    mass_points_to_update = {}
    for marker in markers:
        name = marker.name.lower()
        if name in existing_mp_names:
            mass_points_to_update[name] = mass_points[existing_mp_names[name]]

    del mass_points[:]

    # update the mass points and/or make new ones
    for marker in markers:
        rotation = quaternion_to_matrix(
            marker.rot_i, marker.rot_j,
            marker.rot_k, marker.rot_w)

        name = marker.name
        if name in existing_mp_names:
            mass_points.append(mass_points_to_update[name])
        else:
            mass_points.append()

        mp = mass_points[-1]
        if name not in existing_mp_names:
            # set default values
            mp.relative_mass = 1.0
            mp.relative_density = 1.0
            mp.friction_parallel_scale = 1.0
            mp.friction_perpendicular_scale = 1.0

        forward = rotation * Matrix(((1, ), (0, ), (0, )))
        up      = rotation * Matrix(((0, ), (0, ), (1, )))
        mp.up[:]       = up[0][0],      up[1][0],      up[2][0]
        mp.forward[:]  = forward[0][0], forward[1][0], forward[2][0]
        mp.position[:] = marker.pos_x/100, marker.pos_y/100, marker.pos_z/100
        mp.name = name
        mp.radius = marker.radius/100
        mp.model_node = marker.parent

    phys_tag.calc_internal_data()

    # reload the window to display the newly entered info
    window.reload()
    app.update_tag_window_title(window)
    if not isfile(tag_path):
        # save the tag if it doesnt already exist
        app.save_tag()

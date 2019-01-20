import zlib

from os.path import dirname, join, relpath, isfile
from tkinter.filedialog import askopenfilename
from traceback import format_exc

from supyr_struct.defs.util import sanitize_path
from supyr_struct.defs.constants import PATHDIV
from reclaimer.enums import hmt_icon_types


icon_type_map = {hmt_icon_types[i]: i for i in range(len(hmt_icon_types))}
MAX_ICON_NAME_LENGTH = max(*(len(name) for name in hmt_icon_types))


def hud_message_text_from_hmt(app, fp=None):
    load_dir = app.last_data_load_dir
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
            filetypes=(("HUD messages", "*.hmt"), ("All", "*")),
            title="Select hmt file to turn into a hud_message_text tag")

    if not fp:
        return

    message_strings = {}
    message_names = []
    try:
        fp = sanitize_path(fp)
        app.last_data_load_dir = dirname(fp)

        print("Creating hud_message_text from this hmt file:")
        print("    %s" % fp)
        with open(fp, "r", encoding="utf-16-le") as f:
            hmt_string_data = f.read().lstrip('\ufeff').split("\n")

        line_num = 0
        for line in hmt_string_data:
            line_num += 1
            if not line:
                continue
            elif "=" in line:
                name, message = line.split("=", 1)
            else:
                name, message = line, ""

            if name in message_strings:
                print("    ERROR: Duplicate message name on line %s" % line_num)
                continue

            if len(name) > 31:
                print(("    WARNING: Message name on line %s is too long. " +
                       "Truncating name to '%s'" ) % (line_num, name[: 31]))
                name = name[: 31]

            if name and message:
                message_strings[name] = message
                message_names.append(name)
            elif name and not message and "=" in line:
                print("    WARNING: Empty message on line %s" % line_num)
                message_strings[name] = ""
                message_names.append(name)
            elif not name and message:
                print("    ERROR: No message name on line %s" % line_num)
            else:
                print("    ERROR: No name or message on line %s" % line_num)

    except Exception:
        print(format_exc())
        print("    Could not load hmt file.")
        return

    if len(message_strings) > 1024:
        print("    ERROR: Too many hud messages. Please remove %s of them." %
              (len(message_strings) - 1024))
        return

    tag_path = dirname(relpath(fp, data_dir))
    rel_tagpath = join(tag_path, "hud messages.hud_message_text")
    if not tag_path.startswith(".."):
        tag_path = join(tags_dir, rel_tagpath)
    else:
        tag_path = ""

    if isfile(tag_path):
        print("    Updating existing hud_message_text tag.")
        tag_load_path = (tag_path, )
    else:
        print("    Creating new hud_message_text tag.")
        tag_load_path = ""

    # make the tag window
    window = app.load_tags(filepaths=tag_load_path, def_id='hmt ')
    if not window:
        return

    window = window[0]
    hmt__tag = window.tag

    window.is_new_tag = False
    hmt__tag.filepath = tag_path
    hmt__tag.rel_filepath = rel_tagpath

    tagdata = hmt__tag.data.tagdata
    elements = tagdata.message_elements.STEPTREE
    messages = tagdata.messages.STEPTREE
    tagdata.string.data = ""
    del elements[:]
    del messages[:]

    error = False
    if len(elements) > 8192:
        print("    ERROR: Too many message elements. " +
              "Please simplify your messages.")
        error = True

    text_blob = ""
    for name in message_names:
        message_string = message_strings[name]

        messages.append()
        message = messages[-1]
        message.name = name
        message.text_start = len(text_blob)
        message.element_index = len(elements)

        if len(message_string) == 0:
            elements.append()
            element = elements[-1]
            element.data.set_active("text")
            element.data.text.data = 1  # set length to 1
            message.element_count = 1
            text_blob += "\x00"
            continue

        i = 0
        while i < len(message_string):
            elements.append()
            element = elements[-1]
            message.element_count += 1

            element_base = i
            icon_name = ""
            curr_text = ""
            c = message_string[i]
            if c == "%":
                element.type.set_to("icon")
                element.data.set_active("icon")
            else:
                element.type.set_to("text")
                element.data.set_active("text")
                curr_text += c

            i += 1
            element_type = element.type.enum_name
            while (i < len(message_string) and
                   len(curr_text) < 254 and
                   len(icon_name) < MAX_ICON_NAME_LENGTH):
                c = message_string[i]
                if c == "%":
                    break

                i += 1
                if element_type == "text":
                    curr_text += c
                else:
                    icon_name += c
                    if icon_name in icon_type_map:
                        break

            if element_type == "text":
                # add the delimiter
                element.data.text.data = len(curr_text) + 1
                text_blob += curr_text + "\x00"
            elif icon_name in icon_type_map:
                element.data.icon.data = icon_type_map[icon_name]
            else:
                print("    WARNING: Unknown icon type specified in message '%s'" % name)
                i = element_base + 1
                del elements[-1]
                message.element_count -= 1


    if len(text_blob) > 32768:
        print(("    ERROR: String data too large by %s characters. " +
              "Please simplify your messages.") %
              (len(text_blob) - 32768))
        error = True


    # replace the string data
    tagdata.string.data = text_blob

    # reload the window to display the newly entered info
    window.reload()
    app.update_tag_window_title(window)
    if error:
        print("    Errors occurred while compiling. " +
              "Tag will not be automatically saved.")
        window.is_new_tag = True
    elif not isfile(tag_path):
        # save the tag if it doesnt already exist
        app.save_tag()


from os.path import dirname, join, isfile, splitext
from tkinter.filedialog import askopenfilename
from traceback import format_exc
from struct import unpack, pack

from binilla.util import *
from binilla.widgets import BinillaWidget
from reclaimer.data_extraction import extract_h1_scnr_data
from supyr_struct.defs.constants import *

curr_dir = get_cwd(__file__)

class SauceRemovalWindow(BinillaWidget, tk.Toplevel):
    app_root = None
    handler = None

    print_interval = 5

    def __init__(self, app_root, *args, **kwargs): 
        self.handler = app_root.get_handler("Halo 1 OS v4")
        self.app_root = app_root
        kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)
        tk.Toplevel.__init__(self, app_root, *args, **kwargs)

        self.title("Scenario Open Sauce Scrubber Tool")
        self.geometry("400x80+0+0")
        self.resizable(0, 0)
        self.update()
        try:
            try:
                self.iconbitmap(join(curr_dir, '..', 'mozzarilla.ico'))
            except Exception:
                self.iconbitmap(join(curr_dir, 'icons', 'mozzarilla.ico'))
        except Exception:
            print("Could not load window icon.")

        # make the tkinter variables
        self.scenario_path = tk.StringVar(self)

        # make the frames
        self.scenario_frame = tk.LabelFrame(
            self, text="Scenario to remove sauce from")
        self.button_frame = tk.Frame(self)

        self.begin_button = tk.Button(
            self.button_frame, text='Remove sauce',
            width=20, command=self.remove_sauce)
        self.begin_button.tooltip_string = "It's okay, I like buttered noodles too sometimes."

        self.scenario_entry = tk.Entry(
            self.scenario_frame, textvariable=self.scenario_path)
        self.scenario_browse_button = tk.Button(
            self.scenario_frame, text="Browse", command=self.scenario_browse)


        for w in (self.scenario_entry, ):
            w.pack(padx=(4, 0), pady=2, side='left', expand=True, fill='x')

        for w in (self.scenario_browse_button, ):
            w.pack(padx=(0, 4), pady=2, side='left')

        for w in (self.begin_button, ):
            w.pack(padx=4, pady=2, side='left')

        self.scenario_frame.pack(fill='x', padx=1)
        self.button_frame.pack(fill="y")

        self.transient(app_root)
        self.apply_style()
        self.update()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry("%sx%s" % (w, h))
        self.minsize(width=w, height=h)

    def scenario_browse(self):
        dirpath = askopenfilename(
            initialdir=self.scenario_path.get(),
            parent=self, title="Select scenario to remove sauce from")

        if not dirpath:
            return
        self.app_root.last_load_dir = dirname(dirpath)
        self.scenario_path.set(dirpath)

    def destroy(self):
        try:
            self.app_root.tool_windows.pop(self.window_name, None)
        except AttributeError:
            pass
        tk.Toplevel.destroy(self)

    def remove_sauce(self):
        scenario_path = self.scenario_path.get()
        if not isfile(scenario_path):
            print("Scenario path does not point to a file.")
            return

        print("Scrubbing sauce from scenario...")
        try:
            scnr_tag = self.handler.build_tag(filepath=scenario_path)
        except KeyError:
            scnr_tag = None

        if scnr_tag is None:
            print("    Could not load scenario.")
            return

        tagdata = scnr_tag.data.tagdata

        # make and report any changes that will damage the integrity of the tag
        if tagdata.project_yellow_definitions.filepath:
            print("    WARNING: Removing project yelo definitions.")
            tagdata.project_yellow_definitions.filepath = ""

        if tagdata.bsp_modifiers.size > 0:
            print("    WARNING: Removing all bsp modifiers.")
            del tagdata.bsp_modifiers.STEPTREE[:]

        if tagdata.structure_bsps.size > 16:
            print("    WARNING: More than 16 bsps referenced. " +
                  "Removing the last %s" % (tagdata.structure_bsps.size - 16))
            del tagdata.structure_bsps.STEPTREE[16: ]

        syntax_data = tagdata.script_syntax_data.data
        too_large = len(tagdata.script_string_data.data) > 262144

        if not too_large and len(syntax_data) >= 56:
            # see if there are too many nodes
            last_node = unpack(">H", syntax_data[46: 48])[0]
            too_large &= last_node > 19001

        if too_large:
            print("    WARNING: Scripts are too large to fit in a " +
                  "normal scenario. Extracting scripts to the same " +
                  "directory as the scenario.")
            extract_h1_scnr_data(
                tagdata,
                splitext(scenario_path.replace("\\", "/").split("/")[-1])[0],
                out_dir=dirname(scenario_path), engine="yelo")
            tagdata.script_syntax_data.data = b''
            tagdata.script_string_data.data = b''
        else:
            new_syntax_data = syntax_data[: 32] + pack(">H", 19001)
            tagdata.script_syntax_data.data = new_syntax_data + syntax_data[34: 380076]

        scnr_tag.serialize(backup=True, calc_pointers=False, temp=False)
        print("    Finished")

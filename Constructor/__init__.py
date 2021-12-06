import unrealsdk
from unrealsdk import *

from ..ModMenu import SDKMod

import os
import re
from configparser import ConfigParser

from . import logging, hookmanager, assignor, constructor, hotfix_manager, spawner
from . import custompawns as pawns
from . import matinstconsts as mat
from . import bl2pysave as pysave
from . import bl2tools


class ConstructorMain(SDKMod):
    Name = "Constructor"
    Version = "1.1.0"
    Description = "Mod/Ressource that allows the easy creation and use of new non replacing Objects."
    Author = "Juso"
    Types = unrealsdk.ModTypes.Content | unrealsdk.ModTypes.Utility


    def __init__(self):
        self.ini_works = ConstructorMain.check_willow_engine_ini()
        self.FILE_PATH = os.path.dirname(os.path.realpath(__file__))
        self.config = ConfigParser(comment_prefixes="/", allow_no_value=True)
        self.config.read(os.path.join(self.FILE_PATH, "settings.ini"))
        if self.config.getboolean("main", "optimize_on_startup"):
            self.config.set("main", "optimize_on_startup", "false")
            with open(os.path.join(self.FILE_PATH, "settings.ini"), "w") as f:
                self.config.write(f)
            ConstructorMain.optimize()

        logging.logger = logging.Logger(self.config.get("main", "log_level").strip(),
                                        self.config.getboolean("main", "log_all_calls", fallback=False))

        self.Constructor = constructor.Constructor(self.FILE_PATH)
        self.HotfixMan = hotfix_manager.Hotfixer(self.FILE_PATH)
        self.Pawns = pawns.Pawns(self.FILE_PATH)
        self.Saves = pysave.PySave(self.FILE_PATH)
        self.Assignor = assignor.Assignor(self.FILE_PATH)
        self.Materials = mat.Materials(self.FILE_PATH)
        self.Spawner = spawner.Spawner(self.FILE_PATH)
        self.initial_spawn = True

    def Enable(self) -> None:
        if not self.ini_works:
            pc = bl2tools.get_player_controller()
            pc.GFxUIManager.ShowTrainingDialog(
                "Documents>My Games>Borderlands 2>WillowGame>Config>WillowEngine.ini Please Change "
                "bForceNoMovies=TRUE to bForceNoMovies=FALSE.\nIf you do not change it, Exodus won't work. Make sure "
                "to restart the game after making these changes.",
                "Note", 10)
            raise Exception("Won't enable Exodus with bForceNoMovies .ini Tweak!")

        self.Constructor.Enable()
        self.HotfixMan.Enable()
        self.Pawns.Enable()
        self.Materials.Enable()
        self.Saves.Enable()
        self.Assignor.Enable()
        self.Spawner.Enable()
        hookmanager.instance.Enable()
        logging.logger.info(f"Everything setup and ready to play :)")
        if not self.config.getboolean("main", "has_seen_version_notes"):
            self.config.set("main", "has_seen_version_notes", "true")
            with open(os.path.join(self.FILE_PATH, "settings.ini"), "w") as f:
                self.config.write(f)
            self.show_version_notes()

        def init_spawn(caller: unrealsdk.UObject, function: unrealsdk.UFunction, params: unrealsdk.FStruct) -> bool:
            if self.initial_spawn:
                pc = bl2tools.get_player_controller()
                if pc is not None:
                    hud = pc.GetHUDMovie()
                    if hud is not None:
                        self.initial_spawn = False
                        hud.ClearTrainingText()
                        hud.AddTrainingText("Everything seems to be up and running.\nIf you encounter"
                                            " any issues please report it to me on Discord."
                                            "\n\nGood luck on the hunt, Vault Hunter!",
                                            f"Constructor V.: {self.Version} Is Running",
                                            8.000000, (), "", False, 0,
                                            pc.PlayerReplicationInfo, True)
            return True

        unrealsdk.RegisterHook("WillowGame.WillowHUD.CreateWeaponScopeMovie", "ConstructorRunningMsg", init_spawn)

    def Disable(self) -> None:
        pc = bl2tools.get_player_controller()
        pc.GFxUIManager.ShowTrainingDialog(
            f"If you are trying to disable {self.Name}, this is only possible by closing your game.\n"
            f"This is due to too many changes that cannot be reverted.",
            "Disable", 5)

    @staticmethod
    def optimize() -> None:
        path = os.path.dirname(os.path.realpath(__file__))
        for extension in (".construct", ".loaded", ".mission", ".itempool", ".assign",
                          ".set", ".lootable", ".reward", ".material", ".popdef", ".pawn", ".spawn"):
            with open(os.path.join(path, "src", f"MASTER{extension}"), "w", encoding="cp1252") as master_file:
                for root, dirs, files in os.walk(path):
                    for file in files:
                        if file.split(".")[0] == "MASTER":
                            continue
                        if file.lower().endswith(extension):
                            with open(os.path.join(root, file), encoding="cp1252") as f:
                                for line in f:
                                    if not line.rstrip():
                                        continue
                                    if line.lstrip()[0] != "-":
                                        master_file.write(f"{line.rstrip()}\n")
            for root, dirs, files in os.walk(path):
                for file in files:
                    if file == f"MASTER{extension}":
                        continue
                    if file.lower().endswith(extension):
                        os.remove(os.path.join(root, file))
        hfiles = []
        keys = []
        vals = []
        for root, dirs, filenames in os.walk(path):
            for file in filenames:
                # .definition as alternative suffix support for Exodus
                if file.lower().endswith(".definition") or file.lower().endswith(".blcm"):
                    hfiles.append(os.path.join(root, file))
        SparkServiceConfiguration = None
        set_cmd = "set {} {} ({})\n"
        with open(os.path.join(path, "src", "MASTER.definition"), "w", encoding="cp1252") as merge_fp:
            for file in hfiles:
                with open(file, "r", encoding="cp1252") as fp:
                    for line in fp:
                        if line.lstrip().lower().startswith("set"):
                            if "SparkService" not in line:
                                merge_fp.write(line)
                            else:
                                _split = line.split(maxsplit=3)
                                attr = _split[2]  # set0 Object1 attribute2 value3:
                                to_merge = _split[3].rstrip()
                                if attr.lower() == "keys":
                                    keys.append(to_merge[1:-1])
                                elif attr.lower() == "values":
                                    vals.append(to_merge[1:-1])

            for x in unrealsdk.FindAll("SparkServiceConfiguration"):
                if x.ServiceName == "Micropatch":
                    SparkServiceConfiguration = x.PathName(x)
                    break
            if not SparkServiceConfiguration:
                SparkServiceConfiguration = "Transient.SparkServiceConfiguration_0"
                merge_fp.write("set Transient.SparkServiceConfiguration_0 ServiceName Micropatch\n")
                merge_fp.write("set Transient.SparkServiceConfiguration_0 ConfigurationGroup Default\n")
                gb_acc = unrealsdk.FindAll("GearboxAccountData")[-1]
                merge_fp.write(
                    "set {} Services (Transient.SparkServiceConfiguration_0)\n".format(gb_acc.PathName(gb_acc)))

            # remove double gearbox hotfixes
            all_keys = ",".join(keys)
            all_vals = ",".join(vals)

            pat = re.compile(r"\"([^\"\\]*(?:\\.[^\"\\]*)*)\"")

            gbx_keys = set()
            gbx_vals = set()
            own_keys = list()
            own_vals = list()
            for k, v in zip(re.findall(pat, all_keys), re.findall(pat, all_vals)):
                if k not in gbx_keys:
                    own_keys.append(f"\"{k}\"")
                    own_vals.append(f"\"{v}\"")
                if "gbx_fixes" in k.lower():  # filter out all duplicate gbx hotfixes
                    gbx_keys.add(k)
                    gbx_vals.add(v)

            merge_fp.write(set_cmd.format(SparkServiceConfiguration, "Keys", ",".join(own_keys)))
            merge_fp.write(set_cmd.format(SparkServiceConfiguration, "Values", ",".join(own_vals)))

        for f in hfiles:
            os.remove(f)

    def show_version_notes(self) -> None:
        pc = bl2tools.get_player_controller()
        version_notes = f"Known bugs:\n" \
                        f" - Multiplayer does not work;\n" \
                        f"<font color=\"#A83232\">Note</font>:" \
                        f" Do not activate the <font color=\"#D9CA27\">'Fewer Cutscenes'</font>" \
                        f" .ini edit in BLCMM> Tools> Setup Game Files for Mods! This will disable many 'hotfix'" \
                        f" like features from Exodus, including the loading of your items.\n\n" \
                        f"Same goes for the <font color=\"#D9CA27\">'-nomoviestartup'</font>" \
                        f" flag that you can set to BL2 Launch Options in Steam," \
                        f" do not use this."

        title = f"{self.Name} V.:{self.Version} Notes"
        pc.GFxUIManager.ShowTrainingDialog(version_notes, title, 4)

    @staticmethod
    def check_willow_engine_ini() -> bool:
        ini_path = os.path.join(os.path.expanduser("~"), "Documents", "my games", "Borderlands 2", "WillowGame",
                                "Config")
        try:
            with open(os.path.join(ini_path, "WillowEngine.ini"), "r") as f:
                for line in f:
                    if "bforcenomovies=true" in line.lower():
                        return False
            return True
        except Exception as e:
            unrealsdk.Log(e)
            return True


if __name__.startswith("Mods"):
    unrealsdk.RegisterMod(ConstructorMain())

from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import QFileSystemWatcher
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene
import multiprocessing
import pymem
import pymem.process
import win32con
import win32gui
import json
import os
import sys
import time
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define the folder where the script is located
SCRIPT_DIR = Path(__file__).resolve().parent

__version__=202503181129

DEFAULT_SETTINGS = {
    "esp_rendering": 1,
    "esp_mode": 0, # 0 chỉ vẽ kẻ địch, 1: vẽ kẻ địch và đồng đội
    "hp_bar_rendering": 1,  # 1: vẽ thanh máu, 0: không vẽ
    "armor_bar_rendering": 0, # 1: vẽ giáp, 0: không vẽ
    "bons": 1,  # 1: vẽ xương, 0: không vẽ
    "nickname": 1,  # 1: vẽ tên, 0: không vẽ
    "weapon": 1,  # 1: vẽ vũ khí đang cầm, 0: không vẽ
    "bomb_esp": 1,  # 1: vẽ bom C4, , 0: không vẽ
    "crosshair": 1, # 1: vẽ crosshair
    "crosshair_size": 10,

    "line_rendering": 0, # Inactive
    "head_hitbox_rendering": 0, # Inactive
    "radius": 15, # Inactive
    "keyboard": "C", # Inactive
    "aim_active": 0, # Inactive
    "aim_mode": 1, # Inactive
    "aim_mode_distance": 1, # Inactive
    "trigger_bot_active": 0, # Inactive
    "keyboards": "X", # Inactive
}
BombPlantedTime = 0
BombDefusedTime = 0


def load_settings():
    return DEFAULT_SETTINGS.copy()


def read_json_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logging.info(f"File not found: {file_path}")
        return None
    except json.JSONDecodeError:
        logging.info(f"Error decoding JSON from file: {file_path}")
        return None


def get_offsets_and_client_dll():
    offsets_file = os.path.join(SCRIPT_DIR, "offsets.json")
    client_dll_file = os.path.join(SCRIPT_DIR, "client_dll.json")
    offsets = read_json_file(offsets_file)
    client_dll = read_json_file(client_dll_file)
    return offsets, client_dll


def get_window_size(window_title):
    hwnd = win32gui.FindWindow(None, window_title)
    if hwnd:
        rect = win32gui.GetClientRect(hwnd)
        return rect[2], rect[3]
    return None, None


def w2s(mtx, posx, posy, posz, width, height):
    screenW = (mtx[12] * posx) + (mtx[13] * posy) + (mtx[14] * posz) + mtx[15]
    if screenW > 0.001:
        screenX = (mtx[0] * posx) + (mtx[1] * posy) + (mtx[2] * posz) + mtx[3]
        screenY = (mtx[4] * posx) + (mtx[5] * posy) + (mtx[6] * posz) + mtx[7]
        camX = width / 2
        camY = height / 2
        x = camX + (camX * screenX / screenW)
        y = camY - (camY * screenY / screenW)
        return [int(x), int(y)]
    return [-999, -999]


class ESPWindow(QtWidgets.QWidget):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle('ESP Overlay')
        self.window_width, self.window_height = get_window_size("Counter-Strike 2")
        if self.window_width is None or self.window_height is None:
            logging.info("Lỗi: cửa sổ trò chơi không được tìm thấy.")
            sys.exit(1)
        self.setGeometry(0, 0, self.window_width, self.window_height)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
        hwnd = self.winId()
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT)

        self.offsets, self.client_dll = get_offsets_and_client_dll()
        self.pm = pymem.Pymem("cs2.exe")
        self.client = pymem.process.module_from_name(self.pm.process_handle, "client.dll").lpBaseOfDll

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene, self)
        self.view.setGeometry(0, 0, self.window_width, self.window_height)
        self.view.setRenderHint(QtGui.QPainter.Antialiasing)
        self.view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.view.setStyleSheet("background: transparent;")
        self.view.setSceneRect(0, 0, self.window_width, self.window_height)
        self.view.setFrameShape(QtWidgets.QFrame.NoFrame)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_scene)
        self.timer.start(0)  # Update as fast as possible

        self.last_time = time.time()
        self.frame_count = 0
        self.fps = 0

    def update_scene(self):
        if not self.is_game_window_active():
            self.scene.clear()
            return

        self.scene.clear()
        try:
            esp(self.scene, self.pm, self.client, self.offsets, self.client_dll, self.window_width, self.window_height, self.settings)
            current_time = time.time()
            self.frame_count += 1
            if current_time - self.last_time >= 1.0:
                self.fps = self.frame_count
                self.frame_count = 0
                self.last_time = current_time
            fps_text = self.scene.addText(f"Wall is activated | FPS: {self.fps}", QtGui.QFont('DejaVu Sans', 11, QtGui.QFont.Bold))
            fps_text.setPos(5, 5)
            fps_text.setDefaultTextColor(QtGui.QColor(255, 255, 255))
        except Exception as e:
            logging.info(f"Scene Update Error: {e}")
            QtWidgets.QApplication.quit()

    def is_game_window_active(self):
        hwnd = win32gui.FindWindow(None, "Counter-Strike 2")
        if hwnd:
            foreground_hwnd = win32gui.GetForegroundWindow()
            return hwnd == foreground_hwnd
        return False


def esp(scene, pm, client, offsets, client_dll, window_width, window_height, settings):
    if settings['esp_rendering'] == 0:
        return

    dwEntityList = offsets['client.dll']['dwEntityList']
    dwLocalPlayerPawn = offsets['client.dll']['dwLocalPlayerPawn']
    dwViewMatrix = offsets['client.dll']['dwViewMatrix']
    dwPlantedC4 = offsets['client.dll']['dwPlantedC4']
    m_iTeamNum = client_dll['client.dll']['classes']['C_BaseEntity']['fields']['m_iTeamNum']
    m_lifeState = client_dll['client.dll']['classes']['C_BaseEntity']['fields']['m_lifeState']
    m_pGameSceneNode = client_dll['client.dll']['classes']['C_BaseEntity']['fields']['m_pGameSceneNode']
    m_modelState = client_dll['client.dll']['classes']['CSkeletonInstance']['fields']['m_modelState']
    m_hPlayerPawn = client_dll['client.dll']['classes']['CCSPlayerController']['fields']['m_hPlayerPawn']
    m_iHealth = client_dll['client.dll']['classes']['C_BaseEntity']['fields']['m_iHealth']
    m_iszPlayerName = client_dll['client.dll']['classes']['CBasePlayerController']['fields']['m_iszPlayerName']
    m_pClippingWeapon = client_dll['client.dll']['classes']['C_CSPlayerPawnBase']['fields']['m_pClippingWeapon']
    m_AttributeManager = client_dll['client.dll']['classes']['C_EconEntity']['fields']['m_AttributeManager']
    m_Item = client_dll['client.dll']['classes']['C_AttributeContainer']['fields']['m_Item']
    m_iItemDefinitionIndex = client_dll['client.dll']['classes']['C_EconItemView']['fields']['m_iItemDefinitionIndex']
    m_ArmorValue = client_dll['client.dll']['classes']['C_CSPlayerPawn']['fields']['m_ArmorValue']
    m_vecAbsOrigin = client_dll['client.dll']['classes']['CGameSceneNode']['fields']['m_vecAbsOrigin']
    m_flTimerLength = client_dll['client.dll']['classes']['C_PlantedC4']['fields']['m_flTimerLength']
    m_flDefuseLength = client_dll['client.dll']['classes']['C_PlantedC4']['fields']['m_flDefuseLength']
    m_bBeingDefused = client_dll['client.dll']['classes']['C_PlantedC4']['fields']['m_bBeingDefused']

    view_matrix = [pm.read_float(client + dwViewMatrix + i * 4) for i in range(16)]

    local_player_pawn_addr = pm.read_longlong(client + dwLocalPlayerPawn)
    try:
        local_player_team = pm.read_int(local_player_pawn_addr + m_iTeamNum)
    except:
        return

    no_center_x = window_width / 2
    no_center_y = window_height * 0.9
    entity_list = pm.read_longlong(client + dwEntityList)
    entity_ptr = pm.read_longlong(entity_list + 0x10)

    def bombisplant():
        global BombPlantedTime
        bombisplant = pm.read_bool(client + dwPlantedC4 - 0x8)
        if bombisplant:
            if (BombPlantedTime == 0):
                BombPlantedTime = time.time()
        else:
            BombPlantedTime = 0
        return bombisplant

    def getC4BaseClass():
        plantedc4 = pm.read_longlong(client + dwPlantedC4)
        plantedc4class = pm.read_longlong(plantedc4)
        return plantedc4class

    def getPositionWTS():
        c4node = pm.read_longlong(getC4BaseClass() + m_pGameSceneNode)
        c4posX = pm.read_float(c4node + m_vecAbsOrigin)
        c4posY = pm.read_float(c4node + m_vecAbsOrigin + 0x4)
        c4posZ = pm.read_float(c4node + m_vecAbsOrigin + 0x8)
        bomb_pos = w2s(view_matrix, c4posX, c4posY, c4posZ, window_width, window_height)
        return bomb_pos

    def getBombTime():
        BombTime = pm.read_float(getC4BaseClass() + m_flTimerLength) - (time.time() - BombPlantedTime)
        return BombTime if (BombTime >= 0) else 0

    def isBeingDefused():
        global BombDefusedTime
        BombIsDefused = pm.read_bool(getC4BaseClass() + m_bBeingDefused)
        if (BombIsDefused):
            if (BombDefusedTime == 0):
                BombDefusedTime = time.time()
        else:
            BombDefusedTime = 0
        return BombIsDefused

    def getDefuseTime():
        DefuseTime = pm.read_float(getC4BaseClass() + m_flDefuseLength) - (time.time() - BombDefusedTime)
        return DefuseTime if (isBeingDefused() and DefuseTime >= 0) else 0

    # Crosshair drawing function (image-based only)
    bfont = QtGui.QFont('DejaVu Sans', 10, QtGui.QFont.Bold)

    if settings.get('bomb_esp', 0) == 1:
        if bombisplant():
            BombPosition = getPositionWTS()
            BombTime = getBombTime()
            DefuseTime = getDefuseTime()

            if (BombPosition[0] > 0 and BombPosition[1] > 0):
                if DefuseTime > 0:
                    c4_name_text = scene.addText(f'BOMB {round(BombTime, 2)} | DIF {round(DefuseTime, 2)}', bfont)
                else:
                    c4_name_text = scene.addText(f'BOMB {round(BombTime, 2)}', bfont)
                c4_name_x = BombPosition[0]
                c4_name_y = BombPosition[1]
                c4_name_text.setPos(c4_name_x, c4_name_y)
                c4_name_text.setDefaultTextColor(QtGui.QColor(255, 255, 255))

    for i in range(1, 64):
        try:
            if entity_ptr == 0:
                break

            entity_controller = pm.read_longlong(entity_ptr + 0x78 * (i & 0x1FF))
            if entity_controller == 0:
                continue

            entity_controller_pawn = pm.read_longlong(entity_controller + m_hPlayerPawn)
            if entity_controller_pawn == 0:
                continue

            entity_list_pawn = pm.read_longlong(entity_list + 0x8 * ((entity_controller_pawn & 0x7FFF) >> 0x9) + 0x10)
            if entity_list_pawn == 0:
                continue

            entity_pawn_addr = pm.read_longlong(entity_list_pawn + 0x78 * (entity_controller_pawn & 0x1FF))
            if entity_pawn_addr == 0 or entity_pawn_addr == local_player_pawn_addr:
                continue

            entity_team = pm.read_int(entity_pawn_addr + m_iTeamNum)
            if entity_team == local_player_team and settings['esp_mode'] == 0:
                continue

            entity_hp = pm.read_int(entity_pawn_addr + m_iHealth)
            armor_hp = pm.read_int(entity_pawn_addr + m_ArmorValue)
            if entity_hp <= 0:
                continue

            entity_alive = pm.read_int(entity_pawn_addr + m_lifeState)
            if entity_alive != 256:
                continue

            weapon_pointer = pm.read_longlong(entity_pawn_addr + m_pClippingWeapon)
            weapon_index = pm.read_int(weapon_pointer + m_AttributeManager + m_Item + m_iItemDefinitionIndex)
            weapon_name = get_weapon_name_by_index(weapon_index)

            color = QtGui.QColor(71, 167, 106) if entity_team == local_player_team else QtGui.QColor(196, 30, 58)
            game_scene = pm.read_longlong(entity_pawn_addr + m_pGameSceneNode)
            bone_matrix = pm.read_longlong(game_scene + m_modelState + 0x80)

            try:
                headX = pm.read_float(bone_matrix + 6 * 0x20)
                headY = pm.read_float(bone_matrix + 6 * 0x20 + 0x4)
                headZ = pm.read_float(bone_matrix + 6 * 0x20 + 0x8) + 8
                head_pos = w2s(view_matrix, headX, headY, headZ, window_width, window_height)
                if head_pos[1] < 0:
                    continue

                legZ = pm.read_float(bone_matrix + 28 * 0x20 + 0x8)
                leg_pos = w2s(view_matrix, headX, headY, legZ, window_width, window_height)
                deltaZ = abs(head_pos[1] - leg_pos[1])
                leftX = head_pos[0] - deltaZ // 4
                rightX = head_pos[0] + deltaZ // 4
                rect = scene.addRect(QtCore.QRectF(leftX, head_pos[1], rightX - leftX, leg_pos[1] - head_pos[1]), QtGui.QPen(color, 1), QtCore.Qt.NoBrush)

                if settings['hp_bar_rendering'] == 1:
                    max_hp = 100
                    hp_percentage = min(1.0, max(0.0, entity_hp / max_hp))
                    hp_bar_width = 2
                    hp_bar_height = deltaZ
                    hp_bar_x_left = leftX - hp_bar_width - 2
                    hp_bar_y_top = head_pos[1]
                    hp_bar = scene.addRect(QtCore.QRectF(hp_bar_x_left, hp_bar_y_top, hp_bar_width, hp_bar_height), QtGui.QPen(QtCore.Qt.NoPen), QtGui.QColor(0, 0, 0))
                    current_hp_height = hp_bar_height * hp_percentage
                    hp_bar_y_bottom = hp_bar_y_top + hp_bar_height - current_hp_height
                    hp_bar_current = scene.addRect(QtCore.QRectF(hp_bar_x_left, hp_bar_y_bottom, hp_bar_width, current_hp_height), QtGui.QPen(QtCore.Qt.NoPen),
                                                   QtGui.QColor(255, 0, 0))

                if settings['armor_bar_rendering'] == 1:
                    max_armor_hp = 100
                    armor_hp_percentage = min(1.0, max(0.0, armor_hp / max_armor_hp))
                    armor_bar_width = 2
                    armor_bar_height = deltaZ
                    armor_bar_x_left = leftX - 2 - 2 - armor_bar_width - 2
                    armor_bar_y_top = head_pos[1]

                    armor_bar = scene.addRect(QtCore.QRectF(armor_bar_x_left, armor_bar_y_top, armor_bar_width, armor_bar_height), QtGui.QPen(QtCore.Qt.NoPen),
                                              QtGui.QColor(0, 0, 0))
                    current_armor_height = armor_bar_height * armor_hp_percentage
                    armor_bar_y_bottom = armor_bar_y_top + armor_bar_height - current_armor_height
                    armor_bar_current = scene.addRect(QtCore.QRectF(armor_bar_x_left, armor_bar_y_bottom, armor_bar_width, current_armor_height), QtGui.QPen(QtCore.Qt.NoPen),
                                                      QtGui.QColor(62, 95, 138))

                if settings.get('bons', 0) == 1:
                    draw_bones(scene, pm, bone_matrix, view_matrix, window_width, window_height)

                if settings.get('nickname', 0) == 1:
                    player_name = pm.read_string(entity_controller + m_iszPlayerName, 32)
                    font_size = max(6, min(18, deltaZ / 25))
                    font = QtGui.QFont('DejaVu Sans', font_size, QtGui.QFont.Bold)
                    name_text = scene.addText(player_name, font)
                    text_rect = name_text.boundingRect()
                    name_x = head_pos[0] - text_rect.width() / 2
                    name_y = head_pos[1] - text_rect.height()
                    name_text.setPos(name_x, name_y)
                    name_text.setDefaultTextColor(QtGui.QColor(255, 255, 255))

                if settings.get('weapon', 0) == 1:
                    weapon_name_text = scene.addText(weapon_name, font)
                    text_rect = weapon_name_text.boundingRect()
                    weapon_name_x = head_pos[0] - text_rect.width() / 2
                    weapon_name_y = head_pos[1] + deltaZ
                    weapon_name_text.setPos(weapon_name_x, weapon_name_y)
                    weapon_name_text.setDefaultTextColor(QtGui.QColor(255, 255, 255))

                # Draw crosshair if enabled in settings
                if settings.get('crosshair', 0) == 1:
                    size = settings['crosshair_size']

                    center_x = window_width / 2
                    center_y = window_height / 2

                    # Image-based crosshair
                    crosshair_pixmap = QtGui.QPixmap((SCRIPT_DIR / 'chainlink_crosshair.png').as_posix())

                    # Resize the pixmap based on the size argument
                    scaled_pixmap = crosshair_pixmap.scaled(size * 2, size * 2, QtCore.Qt.KeepAspectRatio)
                    crosshair_item = scene.addPixmap(scaled_pixmap)
                    crosshair_item.setPos(center_x - scaled_pixmap.width() / 2,
                                          center_y - scaled_pixmap.height() / 2)

                if 'radius' in settings:
                    if settings['radius'] != 0:
                        center_x = window_width / 2
                        center_y = window_height / 2
                        screen_radius = settings['radius'] / 100.0 * min(center_x, center_y)
                        ellipse = scene.addEllipse(QtCore.QRectF(center_x - screen_radius, center_y - screen_radius, screen_radius * 2, screen_radius * 2), QtGui.QPen(QtGui.QColor(255, 255, 255, 100), 0.5), QtCore.Qt.NoBrush)

            except:
                return
        except:
            return


def get_weapon_name_by_index(index):
    weapon_names = {
        32: "P2000",
        61: "USP-S",
        4: "Glock",
        2: "Dual Berettas",
        36: "P250",
        30: "Tec-9",
        63: "CZ75-Auto",
        1: "Desert Eagle",
        3: "Five-SeveN",
        64: "R8",
        35: "Nova",
        25: "XM1014",
        27: "MAG-7",
        29: "Sawed-Off",
        14: "M249",
        28: "Negev",
        17: "MAC-10",
        23: "MP5-SD",
        24: "UMP-45",
        19: "P90",
        26: "Bizon",
        34: "MP9",
        33: "MP7",
        10: "FAMAS",
        16: "M4A4",
        60: "M4A1-S",
        8: "AUG",
        13: "Galil",
        7: "AK",
        39: "SG 553",
        40: "SSG 08",
        9: "AWP",
        38: "SCAR-20",
        11: "G3SG1",
        43: "Flashbang",
        44: "Hegrenade",
        45: "Smoke",
        46: "Molotov",
        47: "Decoy",
        48: "Incgrenage",
        49: "C4",
        31: "Taser",
        42: "Knife",
        41: "Knife Gold",
        59: "Knife",
        80: "Knife Ghost",
        500: "Knife Bayonet",
        505: "Knife Flip",
        506: "Knife Gut",
        507: "Knife Karambit",
        508: "Knife M9",
        509: "Knife Tactica",
        512: "Knife Falchion",
        514: "Knife Survival Bowie",
        515: "Knife Butterfly",
        516: "Knife Rush",
        519: "Knife Ursus",
        520: "Knife Gypsy Jackknife",
        522: "Knife Stiletto",
        523: "Knife Widowmaker"
    }
    return weapon_names.get(index, 'Unknown')


def draw_bones(scene, pm, bone_matrix, view_matrix, width, height):
    bone_ids = {
        "head": 6,
        "neck": 5,
        "spine": 4,
        "pelvis": 0,
        "left_shoulder": 13,
        "left_elbow": 14,
        "left_wrist": 15,
        "right_shoulder": 9,
        "right_elbow": 10,
        "right_wrist": 11,
        "left_hip": 25,
        "left_knee": 26,
        "left_ankle": 27,
        "right_hip": 22,
        "right_knee": 23,
        "right_ankle": 24,
    }
    bone_connections = [
        ("head", "neck"),
        ("neck", "spine"),
        ("spine", "pelvis"),
        ("pelvis", "left_hip"),
        ("left_hip", "left_knee"),
        ("left_knee", "left_ankle"),
        ("pelvis", "right_hip"),
        ("right_hip", "right_knee"),
        ("right_knee", "right_ankle"),
        ("neck", "left_shoulder"),
        ("left_shoulder", "left_elbow"),
        ("left_elbow", "left_wrist"),
        ("neck", "right_shoulder"),
        ("right_shoulder", "right_elbow"),
        ("right_elbow", "right_wrist"),
    ]
    bone_positions = {}
    try:
        for bone_name, bone_id in bone_ids.items():
            boneX = pm.read_float(bone_matrix + bone_id * 0x20)
            boneY = pm.read_float(bone_matrix + bone_id * 0x20 + 0x4)
            boneZ = pm.read_float(bone_matrix + bone_id * 0x20 + 0x8)
            bone_pos = w2s(view_matrix, boneX, boneY, boneZ, width, height)
            if bone_pos[0] != -999 and bone_pos[1] != -999:
                bone_positions[bone_name] = bone_pos
        for connection in bone_connections:
            if connection[0] in bone_positions and connection[1] in bone_positions:
                scene.addLine(
                    bone_positions[connection[0]][0], bone_positions[connection[0]][1],
                    bone_positions[connection[1]][0], bone_positions[connection[1]][1],
                    QtGui.QPen(QtGui.QColor(255, 255, 255, 200), 1)
                )
    except Exception as e:
        logging.info(f"Error drawing bones: {e}")


def esp_main():
    settings = load_settings()
    app = QtWidgets.QApplication(sys.argv)
    window = ESPWindow(settings)
    window.show()
    sys.exit(app.exec())


def connect_cs2():
    connected = False
    process_name = 'cs2.exe'
    while not connected:
        try:
            pm = pymem.Pymem(process_name)
            client = pymem.process.module_from_name(pm.process_handle, "client.dll").lpBaseOfDll
            connected = True
            logging.info(f"Connected to {process_name}.")
        except Exception as e:
            logging.info(f"Waiting for {process_name} to start...")
            time.sleep(10)


if __name__ == "__main__":
    logging.info("All code are updated")

    # check open cs2
    connect_cs2()

    # start wall
    logging.info("Starting Wall!")
    time.sleep(1)
    process2 = multiprocessing.Process(target=esp_main)
    process2.start()
    process2.join()

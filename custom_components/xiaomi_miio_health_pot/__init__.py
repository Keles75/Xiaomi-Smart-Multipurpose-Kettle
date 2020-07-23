'''
@Author        : fineemb
@Github        : https://github.com/fineemb
@Description   : run_status: 16(No kettle placed)0(Normal)32(Drycooking protection)48(Two errors together)
@Date          : 2020-07-23 17:14:14
@LastEditors   : Keles75
@LastEditTime  : 2020-07-23 17:14:14
'''
from collections import defaultdict
import asyncio
from datetime import timedelta
from functools import partial
import logging

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.helpers import discovery
from homeassistant.const import (
    CONF_NAME,
    CONF_HOST,
    CONF_TOKEN,
    CONF_SCAN_INTERVAL,
    ATTR_ENTITY_ID,
)
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.event import track_time_interval
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.util.dt import utcnow
from miio import Device, DeviceException

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "Mi Smart Multipurpose Kettle"
DOMAIN = "health_pot"
DATA_KEY = "health_pot_data"
DATA_TEMPERATURE_HISTORY = "temperature_history"
DATA_STATE = "state"

STATE_1 = "1"
STATE_2 = "2"
STATE_3 = "3"
STATE_4 = "4"
STATE_5 = "5"

MODE_11 = "Herbal tea" # Травяной чай
MODE_12 = "Fruit tea" # фруктовый чай
MODE_13 = "Simmered soup" # Суп
MODE_14 = "Medicinal food" # Лечебная диета
MODE_15 = "Congee" # Congee
MODE_16 = "Edible bird's nest" # Edible bird's nest
MODE_17 = "Hotpot" # Hotpot
MODE_18 = "boiled_water" # Вскипятить воду
MODE_19 = "Warm milk" # Теплое молоко
MODE_20 = "Soft-boiled egg" # Яйца всмятку
MODE_21 = "Yogurt" # Yogurt
MODE_22 = "Steamed egg" # Яйца вкрутую
MODE_23 = "brewed_tea" # Заварить чай
MODE_24 = "Ganoderma" # Ganoderma
MODE_25 = "Disinfect" # Дезинфицировать
MODE_26 = "Sweet soup" # Sweet soup
MODE_1 = "Custom1" # Custom1
MODE_2 = "Custom2" # Custom2
MODE_3 = "Custom3" # Custom3
MODE_4 = "Custom4" # Custom4
MODE_5 = "Custom5" # Custom5
MODE_6 = "Custom6" # Custom6
MODE_7 = "Custom7" # Custom7
MODE_8 = "Custom8" # Custom8

SERVICE_SET_VOICE = "set_voice"
SERVICE_SET_WORK = "set_work"
SERVICE_DELETE_MODES = "delete_modes"
SERVICE_SET_MODE_SORT = "set_mode_sort"
SERVICE_SET_MODE = "set_mode"

ATTR_MODEID = "id"
ATTR_MODETEMP = "temp"
ATTR_MODETIME = "time"
ATTR_DELMODES = "modes"
ATTR_VOICE = "voice"
ATTR_MODE_SORT = "sort"
ATTR_WORK_STATUS = "status"
ATTR_WORK_MODEID = "id"
ATTR_WORK_KTEMP = "keep_temp"
ATTR_WORK_KTIME = "keep_time"
ATTR_WORK_TS = "timestamp"

SCAN_INTERVAL = timedelta(seconds=30)

CONF_MODEL = "model"

MODEL_NORMAL1 = "viomi.health_pot.v1"

SUPPORTED_MODELS = [
    MODEL_NORMAL1
]

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Required(CONF_TOKEN): vol.All(
                    cv.string, vol.Length(min=32, max=32)
                ),
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Optional(CONF_MODEL): vol.In(SUPPORTED_MODELS),
                vol.Optional(CONF_SCAN_INTERVAL, default=SCAN_INTERVAL): cv.time_period,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

SERVICE_SCHEMA_SET_MODE = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.entity_id,
    vol.Required(ATTR_MODEID): vol.All(vol.Coerce(int), vol.Range(min=1, max=8)),
    vol.Required(ATTR_MODETEMP): vol.All(vol.Coerce(int), vol.Range(min=1, max=99)),
    vol.Required(ATTR_MODETIME): vol.All(vol.Coerce(int), vol.Range(min=1, max=240))
})
SERVICE_SCHEMA_SET_WORK = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.entity_id,
    vol.Required(ATTR_WORK_STATUS): vol.All(vol.Coerce(int), vol.Range(min=1, max=5)),
    vol.Required(ATTR_WORK_MODEID): vol.All(vol.Coerce(int), vol.Range(min=1, max=26)),
    vol.Required(ATTR_WORK_KTEMP): vol.All(vol.Coerce(int), vol.Range(min=40, max=95)),
    vol.Required(ATTR_WORK_KTIME): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
    vol.Required(ATTR_WORK_TS, default=0): vol.All(vol.Coerce(int))
})

SERVICE_SCHEMA_DEL_MODES = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.entity_id,
    vol.Required(ATTR_DELMODES): vol.All(vol.Coerce(int), vol.Range(min=1, max=8))
})
SERVICE_SCHEMA_SET_VOICE = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.entity_id,
    vol.Required(ATTR_VOICE): vol.All(vol.Coerce(str), vol.Clamp('off', 'on'))
})
SERVICE_SCHEMA_SET_MODE_SORT = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.entity_id,
    vol.Required(ATTR_MODE_SORT): vol.All(vol.Coerce(str))
})


ATTR_MODEL = "model"
ATTR_PROFILE = "profile"
SUCCESS = ["ok"]

SERVICE_SCHEMA = vol.Schema(
    {
        #    vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
    }
)
SERVICE_SCHEMA_START = SERVICE_SCHEMA.extend({vol.Required(ATTR_PROFILE): cv.string})

SERVICE_START = "start"
SERVICE_STOP = "stop"

def setup(hass, config):
    from miio import Device, DeviceException
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    host = config[DOMAIN][CONF_HOST]
    token = config[DOMAIN][CONF_TOKEN]
    name = config[DOMAIN][CONF_NAME]
    model = config[DOMAIN].get(CONF_MODEL)
    scan_interval = config[DOMAIN][CONF_SCAN_INTERVAL]

    if DATA_KEY not in hass.data:
        hass.data[DATA_KEY] = {}
        hass.data[DATA_KEY][host] = {}
    
    _LOGGER.info("Initializing with host %s (token %s...)", host, token[:5])
    
    devices = []
    if model is None:
        try:
            miio_device = Device(host, token)
            device_info = miio_device.info()
            model = device_info.model
            _LOGGER.info(
                "%s %s %s detected",
                model,
                device_info.firmware_version,
                device_info.hardware_version,
            )
        except DeviceException:
            raise PlatformNotReady
        
    if model not in SUPPORTED_MODELS:

        _LOGGER.error(
            "Unsupported device found! Please create an issue at "
            "https://github.com/fineemb/Xiaomi-Smart-Multipurpose-Kettle/issues "
            "and provide the following data: %s",
            model,
        )
        return False

    def update(event_time):
        """Get the latest data and updates the states."""
        try:
            miio_device = Device(host, token)

            run_status    =  miio_device.send('get_prop', ["run_status"])[0]
            work_status   =  miio_device.send('get_prop', ["work_status"])[0]
            warm_data     =  miio_device.send('get_prop', ["warm_data"])[0]
            last_time     =  miio_device.send('get_prop', ["last_time"])[0]
            last_temp     =  miio_device.send('get_prop', ["last_temp"])[0]
            curr_tempe    =  miio_device.send('get_prop', ["curr_tempe"])[0]
            # work_temps    =  miio_device.send('get_prop', ["work_temps"])[0]
            mode          =  miio_device.send('get_prop', ["mode"])[0]
            heat_power    =  miio_device.send('get_prop', ["heat_power"])[0]
            warm_time     =  miio_device.send('get_prop', ["warm_time"])[0] 
            cook_time     =  miio_device.send('get_prop', ["cook_time"])[0]
            left_time     =  miio_device.send('get_prop', ["left_time"])[0]
            cook_status   =  miio_device.send('get_prop', ["cook_status"])[0]
            cooked_time   =  miio_device.send('get_prop', ["cooked_time"])[0]
            voice         =  miio_device.send('get_prop', ["voice"])[0]
            stand_top_num =  miio_device.send('get_prop', ["stand_top_num"])[0]
            mode_sort     =  miio_device.send('get_prop', ["mode_sort"])[0]

            __run_status = int(run_status)
            __work_status = int(work_status)
            __last_time = int(last_time)
            __last_temp = int(last_temp)
            __curr_tempe = int(curr_tempe)
            __work_status_cn = None
            __mode_cn = None
            __mode_en = None
            __mode = int(mode)
            __heat_power = int(heat_power)
            __warm_time = int(warm_time)
            __cook_time = int(cook_time)
            __left_time = int(left_time)
            __cook_status = int(cook_status)
            __cooked_time = int(cooked_time)
            __voice = int(voice)
            __stand_top_num = int(stand_top_num)
            __mode_sort = str(mode_sort)
            __warm_data = str(warm_data)
            # __work_temps = int(work_temps)

            if work_status == 1:
                # Reservation
                __current_operation = STATE_1
                __work_status_cn = "Reservation"
            elif work_status == 2:
                # 烹饪
                __current_operation = STATE_2
                __work_status_cn = "Готовка"
            elif work_status == 3:
                # Пауза
                __current_operation = STATE_3
                __work_status_cn = "Пауза"
            elif work_status == 4:
                # Подогрев
                __current_operation = STATE_4
                __work_status_cn = "Подогрев"
            elif work_status == 5:
                # Стоп
                __current_operation = STATE_4
                __work_status_cn = "Стоп"

            if mode == 11:
                # Травяной чай
                __mode_en = MODE_11
                __mode_cn = "Травяной чай"
            elif mode == 12:
                # фруктовый чай
                __mode_en = MODE_12
                __mode_cn = "Фруктовый чай"
            elif mode == 13:
                # Суп
                __mode_en = MODE_13
                __mode_cn = "Суп"
            elif mode == 14:
                # Лечебная диета
                __mode_en = MODE_14
                __mode_cn = "Лечебная диета"
            elif mode == 15:
                # Congee
                __mode_en = MODE_15
                __mode_cn = "Congee"
            elif mode == 16:
                # Edible bird's nest
                __mode_en = MODE_16
                __mode_cn = "Edible bird's nest"
            elif mode == 17:
                # Hotpot
                __mode_en = MODE_17
                __mode_cn = "Hotpot"
            elif mode == 18:
                # Кипячение
                __mode_en = MODE_18
                __mode_cn = "Кипячение"
            elif mode == 19:
                # Теплое молоко
                __mode_en = MODE_19
                __mode_cn = "Теплое молоко"
            elif mode == 20:
                # Яйца в смятку
                __mode_en = MODE_20
                __mode_cn = "Яйца всмятку"
            elif mode == 21:
                # Йогурт
                __mode_en = MODE_21
                __mode_cn = "Йогурт"
            elif mode == 22:
                # Яйца в крутую
                __mode_en = MODE_22
                __mode_cn = "Яйца вкрутую"
            elif mode == 23:
                # Заварить чай
                __mode_en = MODE_23
                __mode_cn = "Заварить чай"
            elif mode == 24:
                # Ganoderma
                __mode_en = MODE_24
                __mode_cn = "Ganoderma"
            elif mode == 25:
                # Disinfect
                __mode_en = MODE_25
                __mode_cn = "Дезинфицировать"
            elif mode == 26:
                # Sweet soup
                __mode_en = MODE_26
                __mode_cn = "Sweet soup"
            elif mode == 1:
                # Custom
                __mode_en = MODE_1
                __mode_cn = "Custom1"
            elif mode == 2:
                # Custom
                __mode_en = MODE_2
                __mode_cn = "Custom2"
            elif mode == 3:
                # 自定义
                __mode_en = MODE_3
                __mode_cn = "Custom3"
            elif mode == 4:
                # 自定义
                __mode_en = MODE_4
                __mode_cn = "Custom4"
            elif mode == 5:
                # 自定义
                __mode_en = MODE_5
                __mode_cn = "Custom5"
            elif mode == 6:
                # 自定义
                __mode_en = MODE_6
                __mode_cn = "Custom6"
            elif mode == 7:
                # 自定义
                __mode_en = MODE_7
                __mode_cn = "Custom7"
            elif mode == 8:
                # 自定义
                __mode_en = MODE_8
                __mode_cn = "Custom8"

            __state_attrs = {
                "run_status":run_status,
                "work_status":work_status,
                "work_status_cn":__work_status_cn,
                "warm_data":warm_data,
                "last_time":last_time,
                "last_temp":last_temp,
                "curr_tempe":curr_tempe,
                # "work_temps":work_temps,
                "mode":mode,
                "mode_en":__mode_en,
                "mode_cn":__mode_cn,
                "heat_power":heat_power,
                "warm_time":warm_time,
                "cook_time":cook_time,
                "left_time":left_time,
                "cook_status":cook_status,
                "cooked_time":cooked_time,
                "voice":voice,
                "stand_top_num":stand_top_num,
                "mode_sort":mode_sort,
                "friendly_name":name
            }

            unique_id = "{}_{}".format("xiaomi", miio_device.info().mac_address.replace(':', ''))
            entityid = "{}.{}".format(DOMAIN,unique_id)
            hass.states.set(entityid, work_status, __state_attrs)

        except DeviceException:
            _LOGGER.exception('Fail to get_prop from XiaomiHealthPot')
            raise PlatformNotReady

    track_time_interval(hass, update, scan_interval)

    def set_voice(voice: str):
        try:
            miio_device = Device(host, token)
            if voice == 'on':
                miio_device.send('set_voice', [0])
            elif voice == 'off':
                miio_device.send('set_voice', [1])
        except DeviceException:
            raise PlatformNotReady
        
    def set_work(**kwargs):
        """Set work."""
        try:
            miio_device = Device(host, token)
            miio_device.send('set_work', [kwargs["status"],kwargs["id"],kwargs["keep_temp"],kwargs["keep_time"],kwargs["timestamp"]])
        except DeviceException:
            raise PlatformNotReady

    def delete_modes(**kwargs):
        """Delete work.删除自定义模式"""
        try:
            miio_device = Device(host, token)
            miio_device.send('delete_modes', [kwargs["modes"]])
        except DeviceException:
            raise PlatformNotReady
    
    def set_mode_sort(**kwargs):
        """Set mode sort.设置模式排序"""
        try:
            miio_device = Device(host, token)
            miio_device.send('set_mode_sort', [kwargs["sort"]])
        except DeviceException:
            raise PlatformNotReady
    
    def set_mode(**kwargs):
        """Set mode.设置自定义模式"""
        try:
            miio_device = Device(host, token)
            miio_device.send('set_mode', [kwargs["id"],kwargs["heat"],kwargs["time"]])
        except DeviceException:
            raise PlatformNotReady

    def service_handle(service):
        params = {key: value for key, value in service.data.items()}

        if service.service == SERVICE_SET_VOICE:
            set_voice(**params)

        if service.service == SERVICE_SET_WORK:
            set_work(**params)

        if service.service == SERVICE_DELETE_MODES:
            delete_modes(**params)

        if service.service == SERVICE_SET_MODE_SORT:
            set_mode_sort(**params)

        if service.service == SERVICE_SET_MODE:
            set_mode(**params)

    hass.services.register(DOMAIN, SERVICE_SET_VOICE, service_handle, schema=SERVICE_SCHEMA_SET_VOICE)
    hass.services.register(DOMAIN, SERVICE_SET_WORK, service_handle, schema=SERVICE_SCHEMA_SET_WORK)
    hass.services.register(DOMAIN, SERVICE_DELETE_MODES, service_handle, schema=SERVICE_SCHEMA_DEL_MODES)
    hass.services.register(DOMAIN, SERVICE_SET_MODE_SORT, service_handle, schema=SERVICE_SCHEMA_SET_MODE_SORT)
    hass.services.register(DOMAIN, SERVICE_SET_MODE, service_handle, schema=SERVICE_SCHEMA_SET_MODE)
    
    return True

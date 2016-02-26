#!/usr/bin/env python
#
# Picture Streamer
#
# This file is part of the Picture Streamer project.
# The program streams image previews from your DSLR or simular
# camera to a web interface, allowing you to download pictures
# the moment they've been taken.
#
# Copyright (C) 2015 Christian Beuschel <chris109@web.de>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA


import BaseHTTPServer
import SocketServer
import gphoto2 as gphoto
import datetime
import os
import sys
import urlparse
import cgi
import avahi
import dbus
import ssl
import subprocess
import Image
import ImageFont
import ImageDraw
import random
import time
import threading
import multiprocessing
import Queue
import httplib


try:
    import NetworkManager
except ImportError:
    NetworkManager = None
    pass

# Global constants

NOTIFY_IMAGELIST_UPDATE = 'NOTIFY_IMAGELIST_UPDATE'


class ThumbnailCreationProcess(multiprocessing.Process):

    JOB_KEY_PICTURE_NAME = 'PictureName'
    JOB_KEY_PICTURE_PATH = 'PicturePath'
    JOB_KEY_THUMBNAIL_PATH = 'ThumbnailPath'

    RESULT_KEY_PICTURE_NAME = 'PictureName'
    RESULT_KEY_SUCCESS = 'Success'

    def __init__(self, job_queue, result_queue):
        super(ThumbnailCreationProcess, self).__init__()
        self._job_queue = job_queue
        self._result_queue = result_queue

    def run(self):
        while True:
            job_dict = self._job_queue.get()
            picture_name = job_dict[self.JOB_KEY_PICTURE_NAME]
            picture_path = job_dict[self.JOB_KEY_PICTURE_PATH]
            thumbnail_path = job_dict[self.JOB_KEY_THUMBNAIL_PATH]
            result_dict = {self.RESULT_KEY_PICTURE_NAME: picture_name,
                           self.RESULT_KEY_SUCCESS: True}
            try:
                size = 600, 600
                image = Image.open(picture_path)
                image.thumbnail(size, Image.ANTIALIAS)
                image.save(thumbnail_path, 'JPEG', quality=75, optimize=True, progressive=True)
            except IOError:
                result_dict[self.RESULT_KEY_SUCCESS] = False
            finally:
                self._result_queue.put(result_dict)
        return


class DemoTetheringProcess(multiprocessing.Process):

    RESULT_KEY_CAMERA_IS_CONNECTED = 'CameraIsConnected'
    RESULT_KEY_SOURCE_PATH = 'SourcePath'
    RESULT_KEY_PICTUE = 'Picture'

    def __init__(self, result_queue, photo_path, initial_counter):
        super(DemoTetheringProcess, self).__init__()
        self._result_queue = result_queue
        self._jpg_counter = initial_counter
        self._photo_path = photo_path

    def create_demo_photo(self, picture_name):
        target_path = os.path.join(self._photo_path, picture_name)
        image_width = 1200
        image_height = 800
        # Choose random colors
        green_color_value = random.random() * 0.8 + 0.2
        red_color_value = random.random() * 0.8 + 0.2
        blue_color_value = random.random() * 0.8 + 0.2
        image = Image.new("RGB", (image_width, image_height), 'black')
        draw = ImageDraw.Draw(image)
        # Draw gradient
        for x in range(image_width):
            for y in range(image_height):
                r = int(green_color_value * (x+1.0) / image_width * 255)
                g = int(red_color_value * (y+1.0) / image_height * 255)
                b = int(blue_color_value * (y+1.0) / (image_height + image_width / 2) * 255)
                color = (r, g, b)
                draw.point((x, y), fill=color)
        # Draw text
        try:
            font = ImageFont.truetype("ClientSideLib/OpenSans-Bold.ttf", 40)
        except IOError:
            font = ImageFont.load_default()
        draw.text(((image_width / 4), (image_height / 2 - 40)), picture_name, font=font)
        # Save image
        image.save(target_path, "JPEG")

    def run(self):
        ticker = 0
        while True:
            if ticker == 4:
                result_dict = {self.RESULT_KEY_CAMERA_IS_CONNECTED: True,
                               self.RESULT_KEY_SOURCE_PATH: None,
                               self.RESULT_KEY_PICTUE: None}
                self._result_queue.put(result_dict)
            elif ticker > 4:
                if (ticker % 7) == 0:
                    # Create new JPEG image
                    self._jpg_counter += 1
                    picture_name = '{0}-IMG_{1:04d}.jpg'.format(time.strftime('%Y-%m-%d-%H-%M-%S'),
                                                                self._jpg_counter)
                    self.create_demo_photo(picture_name)
                    # Process the downloaded picture
                    result_dict = {self.RESULT_KEY_CAMERA_IS_CONNECTED: True,
                                   self.RESULT_KEY_SOURCE_PATH: picture_name,
                                   self.RESULT_KEY_PICTUE: picture_name}
                    self._result_queue.put(result_dict)
            else:
                result_dict = {self.RESULT_KEY_CAMERA_IS_CONNECTED: False,
                               self.RESULT_KEY_SOURCE_PATH: None,
                               self.RESULT_KEY_PICTUE: None}
                self._result_queue.put(result_dict)
            time.sleep(5)
            ticker += 1


class TetheringProcess(multiprocessing.Process):

    RESULT_KEY_CAMERA_IS_CONNECTED = 'CameraIsConnected'
    RESULT_KEY_SOURCE_PATH = 'SourcePath'
    RESULT_KEY_PICTUE = 'Picture'

    def __init__(self, result_queue, photo_path, initial_counter):
        super(TetheringProcess, self).__init__()
        self._result_queue = result_queue
        self._jpg_counter = initial_counter
        self._raw_counter = initial_counter
        self._photo_path = photo_path

    def run(self):
        while True:
            try:
                context = gphoto.Context()
                camera = gphoto.Camera()
                camera.init(context)
                result_dict = {self.RESULT_KEY_CAMERA_IS_CONNECTED: True,
                               self.RESULT_KEY_SOURCE_PATH: None,
                               self.RESULT_KEY_PICTUE: None}
                self._result_queue.put(result_dict)
                while True:
                    event_type, event_data = camera.wait_for_event(1000, context)
                    if event_type == gphoto.GP_EVENT_FILE_ADDED:
                        # Handle new picture
                        source_file_path = event_data
                        source_file_name, source_file_extension = os.path.splitext(source_file_path.name)
                        # Download and save the picture
                        if (source_file_extension == '.JPG') or (source_file_extension == '.jpg'):
                            # Hadle JPEG picture files
                            self._jpg_counter += 1
                            picture_name = '{0}-IMG_{1:04d}.jpg'.format(time.strftime('%Y-%m-%d-%H-%M-%S'),
                                                                        self._jpg_counter)
                            picture_path = os.path.join(self._photo_path, picture_name)
                            camera_file = gphoto.check_result(gphoto.gp_camera_file_get(camera,
                                                                                        source_file_path.folder,
                                                                                        source_file_path.name,
                                                                                        gphoto.GP_FILE_TYPE_NORMAL,
                                                                                        context))
                            camera_file.save(picture_path)
                            source_path = os.path.join(source_file_path.folder, source_file_name)
                            result_dict = {self.RESULT_KEY_CAMERA_IS_CONNECTED: True,
                                           self.RESULT_KEY_SOURCE_PATH: source_path,
                                           self.RESULT_KEY_PICTUE: picture_name}
                            self._result_queue.put(result_dict)
                        else:
                            # Handle RAW picture files
                            self._raw_counter += 1
                            picture_name = '{0}-IMG_{1:04d}{2}'.format(time.strftime('%Y-%m-%d-%H-%M-%S'),
                                                                       self._raw_counter,
                                                                       source_file_extension)
                            picture_path = os.path.join(self._photo_path, picture_name)
                            camera_file = gphoto.check_result(gphoto.gp_camera_file_get(camera,
                                                                                        source_file_path.folder,
                                                                                        source_file_path.name,
                                                                                        gphoto.GP_FILE_TYPE_NORMAL,
                                                                                        context))
                            camera_file.save(picture_path)
                            source_path = os.path.join(source_file_path.folder, source_file_name)
                            result_dict = {self.RESULT_KEY_CAMERA_IS_CONNECTED: True,
                                           self.RESULT_KEY_SOURCE_PATH: source_path,
                                           self.RESULT_KEY_PICTUE: None}
                            self._result_queue.put(result_dict)
                camera.exit(context)
                break
            except gphoto.GPhoto2Error:
                result_dict = {self.RESULT_KEY_CAMERA_IS_CONNECTED: False,
                               self.RESULT_KEY_SOURCE_PATH: None,
                               self.RESULT_KEY_PICTUE: None}
                self._result_queue.put(result_dict)
                time.sleep(5)
                continue

# Notification Center class


class NotificationCenter:

    __INSTANCE = None

    @classmethod
    def shared_instance(cls):
        if cls.__INSTANCE is None:
            cls.__INSTANCE = NotificationCenter()
        return cls.__INSTANCE

    def __init__(self):
        if self.__INSTANCE is not None:
            raise ValueError("An instantiation already exists!")
        self._lock = threading.Lock()
        self._eventDict = {}

    def fire_event(self, event_name):
        with self._lock:
            try:
                event_list = self._eventDict[event_name]
            except KeyError:
                event_list = []
            for event in event_list:
                event.set()

    def assign_event_to_list(self, event, event_name):
        with self._lock:
            try:
                event_list = self._eventDict[event_name]
            except KeyError:
                event_list = []
                self._eventDict[event_name] = event_list
            event_list.append(event)

    def resign_event_from_list(self, event, event_name):
        with self._lock:
            try:
                event_list = self._eventDict[event_name]
            except KeyError:
                raise
            else:
                if event in event_list:
                    event_list.remove(event)

    def wait_once_for_event_with_timeout(self, event_name, timeout):
        event = threading.Event()
        self.assign_event_to_list(event, event_name)
        timeout_timer = threading.Timer(timeout, event.set)
        timeout_timer.start()
        event.wait()
        timeout_timer.cancel()
        self.resign_event_from_list(event, event_name)
        event.clear()

# Configuration class


class Configuration:

    def __init__(self):
        self._script = sys.argv[0]
        self._allKeys = [
            '-port',
            '-daemon',
            '-dir',
            '-session',
            '-sslcert',
            '-log',
            '-demo',
            '-reboot',
            '-shutdown']
        self._config = {
            'HttpPortNumber': 8888,
            'RunAsDaemon': False,
            'RunInDemoMode': False,
            'DataFolder': './PictureDataFolder/',
            'SessionName': '',
            'SSLCertPath': '',
            'LogFilePath': '',
            'ThumbnailFolder': 'Thumbnails',
            'PhotoFolder': 'Photos',
            'RebootCommand': '',
            'ShutdownCommand': ''}

    def print_usage_information_and_exit(self):
        usage = "Usage: {0} [-port <NUMBER>] [-daemon <yes|no>]".format(self._script) + \
                "[-dir <DATA DIRECTORY>] [-session <SESSIONNAME>]" + \
                "[-sslcert <FILE>] -log [LOGFILE] [-demo <yes|no>]"
        print usage
        sys.exit(1)

    def get(self, key):
        return self._config[key]

    def parse_arguments(self, argv):
        is_key = True
        current_key = ''
        for arg in argv:
            if is_key is True:
                if arg in self._allKeys:
                    current_key = arg
                else:
                    self.print_usage_information_and_exit()
                is_key = False
            else:
                if current_key == '-port':
                    if 1024 < int(arg) < 10000:
                        self._config['PortNumber'] = int(arg)
                    else:
                        print "Invalid port number!"
                        exit(1)
                elif current_key == '-daemon':
                    if arg == 'yes':
                        self._config['RunAsDaemon'] = True
                elif current_key == '-demo':
                    if arg == 'yes':
                        self._config['RunInDemoMode'] = True
                elif current_key == '-dir':
                    if os.path.exists(arg) and os.path.isdir(arg) and os.access(arg, os.W_OK):
                        self._config['DataFolder'] = arg
                    else:
                        print "Invalid folder for data!"
                        sys.exit(1)
                elif current_key == '-session':
                    self._config['SessionName'] = str(arg)
                elif current_key == '-sslcert':
                    if os.path.exists(arg) and os.path.isfile(arg):
                        self._config['SSLCertPath'] = arg
                elif current_key == '-log':
                    self._config['LogFilePath'] = str(arg)
                elif current_key == '-reboot':
                    self._config['RebootCommand'] = str(arg)
                elif current_key == '-shutdown':
                    self._config['ShutdownCommand'] = str(arg)
                else:
                    self.print_usage_information_and_exit()
                is_key = True

# Zero conf service class


class ZeroconfService:

    def __init__(self, name, port, stype="_http._tcp", domain="", host="", text=""):
        self._name = name
        self._stype = stype
        self._domain = domain
        self._host = host
        self._port = port
        self._text = text
        self._group = None

    def publish(self):
        bus = dbus.SystemBus()
        server = dbus.Interface(
            bus.get_object(
                avahi.DBUS_NAME,
                avahi.DBUS_PATH_SERVER),
            avahi.DBUS_INTERFACE_SERVER)
        self._group = dbus.Interface(bus.get_object(avahi.DBUS_NAME,
                                                    server.EntryGroupNew()),
                                     avahi.DBUS_INTERFACE_ENTRY_GROUP)
        self._group.AddService(avahi.IF_UNSPEC,
                               avahi.PROTO_UNSPEC,
                               dbus.UInt32(0),
                               self._name,
                               self._stype,
                               self._domain,
                               self._host,
                               dbus.UInt16(self._port),
                               avahi.string_array_to_txt_array(self._text))
        self._group.Commit()

    def unpublish(self):
        self._group.Reset()

# Logger class


class Logger:

    LOG_LEVEL_INFO = 'INFO:'
    LOG_LEVEL_WARN = 'WARNING:'
    LOG_LEVEL_ERROR = 'ERROR:'
    LOG_LEVEL_FATAL = 'FATAL ERROR:'

    def __init__(self, logfile_path, run_as_deamon):
        self._logFilePath = logfile_path
        self._runAsDeamon = run_as_deamon
        self._lock = threading.Lock()

    def log(self, log_level, log_message):
        with self._lock:
            formatted_message = '[{0}] {1} {2}'.format(str(datetime.datetime.now()), log_level, log_message)
            if self._logFilePath != '':
                with open(self._logFilePath, 'a') as logFile:
                    logFile.write("{0}\n".format(formatted_message))
            if self._runAsDeamon is False:
                print(formatted_message)

# Server class


class ThreadingHttpServer(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):
    pass

# HTTP Handler class


class PhotoStreamHttpHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    def do_POST(self):
        app = Application.shared_instance()
        config = app.get_config()
        logger = app.get_logger()

        # Reading variables from GET request
        scheme, netloc, path, params, query, fragment = urlparse.urlparse(self.path)
        post_content_type, post_dict = cgi.parse_header(
            self.headers.getheader('content-type'))
        host, port = self.client_address
        # Reding variables from POST request
        if post_content_type == 'multipart/form-data':
            post_variables = cgi.parse_multipart(self.rfile, post_dict)
        elif post_content_type == 'application/x-www-form-urlencoded':
            post_content_length = int(self.headers.getheader('content-length'))
            post_variables = urlparse.parse_qs(self.rfile.read(post_content_length), keep_blank_values=1)
        else:
            post_variables = {}

        try:
            # Connect hub API
            if path == '/connectHub.api':
                hub_address = host
                hub_port = post_variables['hubPort'][0]
                hub_path = post_variables['hubPath'][0]

                hub_list = app.get_hub_list()
                hub_list.add_hub(hub_address, hub_port, hub_path)

                data = "Established connection to hub"
                "\"http://{0}:{1}{2}\"".format(hub_address, hub_port, hub_path)
                logger.log(Logger.LOG_LEVEL_INFO, data)

            elif path == '/shutdown.api':
                client_address = host
                command = post_variables['command'][0]
                reboot_command = config.get('RebootCommand')
                shutdown_command = config.get('ShutdownCommand')

                if (command == 'reboot') and (reboot_command == ''):
                    data = "OPERATION_NOT_AVAILABLE"
                elif (command == 'shutdown') and (shutdown_command == ''):
                    data = "OPERATION_NOT_AVAILABLE"
                else:
                    if command == 'reboot':
                        data = 'REBOOT'
                        print reboot_command.split(' ')
                        subprocess.call(reboot_command.split(' '))
                        logger.log(Logger.LOG_LEVEL_INFO, "Executing reboot requested by {0}".format(client_address))
                    elif command == 'shutdown':
                        data = 'SHUTDOWN'
                        print shutdown_command.split(' ')
                        subprocess.call(shutdown_command.split(' '))
                        logger.log(Logger.LOG_LEVEL_INFO, "Executing shutdown requested by {0}".format(client_address))
                    else:
                        logger.log(Logger.LOG_LEVEL_INFO, "Invalid requested by {0}".format(client_address))
                        data = "OPERATION_NOT_AVAILABLE"
            else:
                raise IOError

            self.send_response(200)
            self.send_header('Content-Length', '{0}'.format(len(data)))
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Server', 'PictureStreamer')
            self.end_headers()
            self.wfile.write(data)

        except KeyError:
            self.send_error(400, 'Invalid input parameters')
        except IOError:
            logger.log(Logger.LOG_LEVEL_INFO, 'HTTP ERROR 404: File Not Found: %s' % self.path)
            self.send_error(404, 'File Not Found: %s' % self.path)

    def do_GET(self):
        app = Application.shared_instance()
        config = app.get_config()
        logger = app.get_logger()
        shared_photo_list = app.get_phared_photo_list()
        session_path = app.get_session_path()

        # Reading variables from GET request
        scheme, netloc, path, params, query, fragment = urlparse.urlparse(self.path)
        getvars = urlparse.parse_qs(query)
        # Delivering content
        try:
            try:
                client_image_counter = int(getvars['count'][0])
            except KeyError:
                client_image_counter = 0
            requested_file_path = None
            requested_file_name = None
            requested_file_type = None
            data = None
            force_file_download = False
            document_directory = 'ClientSideLib'
            if (path == '/') or (path == '/index.html'):
                requested_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                   document_directory,
                                                   'index.html')
                requested_file_type = 'text/html'
            elif path == '/favicon.png':
                requested_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                   document_directory,
                                                   'favicon_32.png')
                requested_file_type = 'image/png'
            elif path == '/index.css':
                requested_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                   document_directory,
                                                   'index.css')
                requested_file_type = 'text/css'
            elif path == '/index.js':
                requested_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                   document_directory,
                                                   'index.js')
                requested_file_type = 'text/javascript'
            elif path == '/jquery.js':
                requested_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                   document_directory,
                                                   'jquery.js')
                requested_file_type = 'text/javascript'
            elif path == '/data.json':
                image_counter, name_list = shared_photo_list.get_counter_and_photo_list_till(client_image_counter)
                if len(name_list) == 0:
                    if client_image_counter > 0:
                        delay = 21.0
                    else:
                        delay = 2.0
                    notification_center = NotificationCenter.shared_instance()
                    notification_center.wait_once_for_event_with_timeout(NOTIFY_IMAGELIST_UPDATE, delay)
                requested_file_type = 'text/x-json'
                connected = '0'
                if shared_photo_list.get_camera_is_connected() is True:
                    connected = '1'
                image_counter, name_list = shared_photo_list.get_counter_and_photo_list_till(client_image_counter)
                formatted_name_list = []
                for name in name_list:
                    formatted_name = '"{0}"'.format(name)
                    formatted_name_list.append(formatted_name)
                name_list_string = ', '.join(formatted_name_list)
                data = '"isCameraConnected" : {0}, "imageCounter" : {1}, "imageList" : [ {2} ]'.format(connected,
                                                                                                       image_counter,
                                                                                                       name_list_string)
                data = '{' + data + '}'
            elif path.startswith('/thumb/'):
                requested_file_type = 'image/jpeg'
                requested_file_name = os.path.basename(path)
                requested_file_path = os.path.join(session_path, config.get('ThumbnailFolder'), requested_file_name)
            elif path.startswith('/photo/'):
                force_file_download = True
                requested_file_type = 'image/jpeg'
                requested_file_name = os.path.basename(path)
                requested_file_path = os.path.join(session_path, config.get('PhotoFolder'), requested_file_name)
            if requested_file_path is not None:
                f = open(requested_file_path)
                data = f.read()
                f.close()
            elif data is None:
                raise IOError
            self.send_response(200)
            self.send_header('Content-Length', '{0}'.format(len(data)))
            self.send_header('Content-Type', requested_file_type)
            self.send_header('Server', 'PictureStreamer')
            if force_file_download is True:
                self.send_header('Content-Disposition', 'attachment;filename="{0}";'.format(requested_file_name))
            self.end_headers()
            self.wfile.write(data)

        except IOError:
            logger.log(Logger.LOG_LEVEL_INFO, 'HTTP ERROR 404: File Not Found: %s' % self.path)
            self.send_error(404, 'File Not Found: %s' % self.path)

    def log_message(self, message_format, *args):
        return


# Shared Photo List class

class SharedPhotoList:

    def __init__(self):
        self._lock = threading.Lock()
        self._photoList = []
        self._counter = 0
        self._cameraIsConnected = False

    def set_camera_is_connected(self, is_connected):
        with self._lock:
            self._cameraIsConnected = is_connected

    def get_camera_is_connected(self):
        with self._lock:
            is_connected = self._cameraIsConnected
        return is_connected

    def add_picture(self, picture_name):
        with self._lock:
            self._photoList.insert(0, picture_name)
            self._counter += 1
            count = self._counter
        return count

    def get_counter(self):
        with self._lock:
            count = self._counter
        return count

    def get_counter_and_photo_list_limeted_to(self, limit):
        with self._lock:
            result = []
            count = 0
            for fileName in self._photoList:
                if count >= limit:
                    break
                result.append(fileName)
                count += 1
            count = self._counter
        return count, result

    def get_counter_and_photo_list_till(self, limiting_counter):
        with self._lock:
            result = []
            count = self._counter
            for fileName in self._photoList:
                if count <= limiting_counter:
                    break
                result.append(fileName)
                count -= 1
            count = self._counter
        return count, result

# Hub List class


class HubList:

    KEY_PORT = 'KEY_PORT'
    KEY_PATH = 'KEY_PATH'
    KEY_QUEUE = 'KEY_QUEUE'
    KEY_THREAD = 'KEY_THREAD'

    def __init__(self):
        app = Application.shared_instance()
        self._config = app.get_config()
        self._logger = app.get_logger()
        self._sessionPath = app.get_session_path()
        self._lock = threading.Lock()
        self._hubDict = {}
        self._queueList = []

    def add_picture_for_upload(self, target_file_name):
        with self._lock:
            for uploadQueue in self._queueList:
                uploadQueue.put(target_file_name)

    def add_hub(self, hub_address, hub_port, hub_path):
        with self._lock:
            if hub_address in self._hubDict.keys():
                self._hubDict[hub_address][self.KEY_PORT] = hub_port
                self._hubDict[hub_address][self.KEY_PATH] = hub_path
            else:
                upload_queue = Queue.Queue()
                worker_thread = threading.Thread(
                    target=self.work_queue,
                    args=(hub_address, 1))
                worker_thread.daemon = True
                self._hubDict[hub_address] = {
                    self.KEY_PORT: hub_port,
                    self.KEY_PATH: hub_path,
                    self.KEY_QUEUE: upload_queue,
                    self.KEY_THREAD: worker_thread}
                worker_thread.start()
                self._queueList.append(upload_queue)

    def work_queue(self, hub_address, nonsense):
        with self._lock:
            queue = self._hubDict[hub_address][self.KEY_QUEUE]
        hub_is_offline = False
        while True:
            target_file_name = queue.get()
            sleep_time = 0
            while not self.upload_picture_to_hub(target_file_name, hub_address):
                print('Could not upload file', target_file_name, 'to hub', hub_address)
                sleep_time += 5
                time.sleep(sleep_time)
                if sleep_time > 60:
                    hub_is_offline = True
                    break
            queue.task_done()
            if hub_is_offline is True:
                print('Hub', hub_address, 'is not reachable, deleting connection')
                with self._lock:
                    del self._hubDict[hub_address]
                break

    def upload_picture_to_hub(self, target_file_name, hub_address):
        with self._lock:
            port = self._hubDict[hub_address][self.KEY_PORT]
            path = self._hubDict[hub_address][self.KEY_PATH]

        print 'Uploading', target_file_name, 'to', hub_address, ':', port, path

        thumbnail_path = os.path.join(self._sessionPath, self._config.get('ThumbnailFolder'), target_file_name)
        thumb_field_name = 'thumb'
        thumb_file_name = target_file_name
        try:
            file_handler = open(thumbnail_path, 'rb')
            thumb_value = file_handler.read()
            file_handler.close()
        except:
            raise

        photo_path = os.path.join(self._sessionPath, self._config.get('PhotoFolder'), target_file_name)
        photo_field_name = 'photo'
        photo_file_name = target_file_name
        try:
            file_handler = open(photo_path, 'rb')
            photo_value = file_handler.read()
            file_handler.close()
        except:
            raise

        fields = (('Filed1', 'Value1'),
                  ('Filed1', 'Value2'))
        files = ((thumb_field_name, thumb_file_name, thumb_value),
                 (photo_field_name, photo_file_name, photo_value))
        errcode, errmsg, headers, content = self.post_multipart_form(hub_address, port, path, fields, files)
        print errcode, errmsg, headers, content
        return True

    def post_multipart_form(self, host, port, selector, fields, files):
        """
        Post fields and files to an http host as multipart/form-data.
        fields is a sequence of (name, value) elements for regular form fields.
        files is a sequence of (name, filename, value) elements
        for data to be uploaded as files
        Return the server's response page.
        """
        try:
            content_type, body = self.encode_multipart_formdata(fields, files)
            http_object = httplib.HTTP(host, port)
            http_object.putrequest('POST', selector)
            http_object.putheader('Content-Type', content_type)
            http_object.putheader('Content-Length', str(len(body)))
            http_object.endheaders()
            http_object.send(body)
            errcode, errmsg, headers = http_object.getreply()
            content = http_object.file.read()
        except IOError:
            errcode, errmsg, headers, content = None, None, None, None
        return errcode, errmsg, headers, content

    def encode_multipart_formdata(self, fields, files):
        """
        fields is a sequence of (name, value) elements for regular form fields.
        files is a sequence of (name, filename, value) elements for data to be
        uploaded as files
        Return (content_type, body) ready for httplib.HTTP instance
        """
        boundary = '----------ThIs_Is_tHe_bouNdaRY_$'
        crlf = '\r\n'
        body_list_of_lines = []
        for (key, value) in fields:
            body_list_of_lines.append('--' + boundary)
            body_list_of_lines.append('Content-Disposition: form-data; name="%s"' % key)
            body_list_of_lines.append('')
            body_list_of_lines.append(value)
        for (key, filename, value) in files:
            body_list_of_lines.append('--' + boundary)
            body_list_of_lines.append('Content-Disposition: form-data; name="%s"; filename="%s"' % (key, filename))
            body_list_of_lines.append('Content-Type: %s' % 'application/octet-stream')
            body_list_of_lines.append('')
            body_list_of_lines.append(value)
        body_list_of_lines.append('--' + boundary + '--')
        body_list_of_lines.append('')
        body = crlf.join(body_list_of_lines)
        content_type = 'multipart/form-data; boundary=%s' % boundary
        return content_type, body

# Teathering class

class TetheringThread(threading.Thread):

    def __init__(self):
        super(TetheringThread, self).__init__()
        self.daemon = True
        app = Application.shared_instance()
        self._config = app.get_config()
        self._logger = app.get_logger()
        self._picture_list = app.get_phared_photo_list()
        self._sessionPath = app.get_session_path()
        self._hubList = app.get_hub_list()
        self._notificationCenter = NotificationCenter.shared_instance()
        # Teathering
        self._tethering_result_queue = multiprocessing.Queue()
        self._tethering_process = None
        # Thumbnail creation
        self._thumb_creator_job_queue = multiprocessing.Queue()
        self._thumb_creator_result_queue = multiprocessing.Queue()
        self._thumb_creator_process = None
        self._thumb_creator_result_receiver = None

    def tethering_watchdog(self):
        while True:
            if not self._tethering_process.is_alive():
                self._logger.log(Logger.LOG_LEVEL_WARN, "Tethering process has crashed, restarting it")
                photo_path = os.path.join(self._sessionPath, self._config.get('PhotoFolder'))
                counter = self._picture_list.get_counter()
                self._tethering_process = TetheringProcess(self._tethering_result_queue, photo_path, counter)
                self._tethering_process.start()
            time.sleep(5)

    def receive_thumb_creator_result(self):
        while True:
            result_dict = self._thumb_creator_result_queue.get()
            picture_name = result_dict[ThumbnailCreationProcess.RESULT_KEY_PICTURE_NAME]
            success = result_dict[ThumbnailCreationProcess.RESULT_KEY_SUCCESS]
            if success is True:
                self._logger.log(Logger.LOG_LEVEL_INFO, 'Created thumnail of "{0}"'.format(picture_name))
                self._picture_list.add_picture(picture_name)
                self._notificationCenter.fire_event(NOTIFY_IMAGELIST_UPDATE)
            else:
                self._logger.log(Logger.LOG_LEVEL_ERROR, 'Could not create thumbnail of "{0}"'.format(picture_name))

    def process_picture(self, picture_name):
        picture_path = os.path.join(self._sessionPath,
                                    self._config.get('PhotoFolder'),
                                    picture_name)
        thumbnail_path = os.path.join(self._sessionPath,
                                      self._config.get('ThumbnailFolder'),
                                      picture_name)
        job_dict = {ThumbnailCreationProcess.JOB_KEY_PICTURE_NAME: picture_name,
                    ThumbnailCreationProcess.JOB_KEY_PICTURE_PATH: picture_path,
                    ThumbnailCreationProcess.JOB_KEY_THUMBNAIL_PATH: thumbnail_path}
        self._thumb_creator_job_queue.put(job_dict)

    def run_in_demo_mode(self):
        self._thumb_creator_result_receiver = threading.Thread(target=self.receive_thumb_creator_result)
        self._thumb_creator_result_receiver.setDaemon(True)
        self._thumb_creator_result_receiver.start()
        self._thumb_creator_process = ThumbnailCreationProcess(self._thumb_creator_job_queue,
                                                               self._thumb_creator_result_queue)
        self._thumb_creator_process.start()
        photo_path = os.path.join(self._sessionPath, self._config.get('PhotoFolder'))
        counter = self._picture_list.get_counter()
        self._tethering_process = DemoTetheringProcess(self._tethering_result_queue, photo_path, counter)
        self._tethering_process.start()
        while True:
            result_dict = self._tethering_result_queue.get()
            camera_is_connected = result_dict[DemoTetheringProcess.RESULT_KEY_CAMERA_IS_CONNECTED]
            camera_has_been_connected = self._picture_list.get_camera_is_connected()
            if camera_is_connected is not camera_has_been_connected:
                self._picture_list.set_camera_is_connected(camera_is_connected)
                self._notificationCenter.fire_event(NOTIFY_IMAGELIST_UPDATE)
                if camera_is_connected is True:
                    self._logger.log(Logger.LOG_LEVEL_INFO, 'Camera is connected')
                else:
                    self._logger.log(Logger.LOG_LEVEL_WARN, 'No camera connected')
            source_file_path = result_dict[DemoTetheringProcess.RESULT_KEY_SOURCE_PATH]
            if source_file_path is not None:
                self._logger.log(Logger.LOG_LEVEL_INFO, 'New file "{0}" on camera'.format(source_file_path))
            picture_name = result_dict[DemoTetheringProcess.RESULT_KEY_PICTUE]
            if picture_name is not None:
                self._logger.log(Logger.LOG_LEVEL_INFO, 'Downloaded picture "{0}"'.format(picture_name))
                self.process_picture(picture_name)

    def run_in_productive_mode(self):
        self._thumb_creator_result_receiver = threading.Thread(target=self.receive_thumb_creator_result)
        self._thumb_creator_result_receiver.setDaemon(True)
        self._thumb_creator_result_receiver.start()
        self._thumb_creator_process = ThumbnailCreationProcess(self._thumb_creator_job_queue,
                                                               self._thumb_creator_result_queue)
        self._thumb_creator_process.start()
        photo_path = os.path.join(self._sessionPath, self._config.get('PhotoFolder'))
        counter = self._picture_list.get_counter()
        self._tethering_process = TetheringProcess(self._tethering_result_queue, photo_path, counter)
        self._tethering_process.start()
        tethering_watchdog = threading.Thread(target=self.tethering_watchdog)
        tethering_watchdog.setDaemon(True)
        tethering_watchdog.start()
        while True:
            result_dict = self._tethering_result_queue.get()
            camera_is_connected = result_dict[TetheringProcess.RESULT_KEY_CAMERA_IS_CONNECTED]
            camera_has_been_connected = self._picture_list.get_camera_is_connected()
            if camera_is_connected is not camera_has_been_connected:
                self._picture_list.set_camera_is_connected(camera_is_connected)
                self._notificationCenter.fire_event(NOTIFY_IMAGELIST_UPDATE)
                if camera_is_connected is True:
                    self._logger.log(Logger.LOG_LEVEL_INFO, 'Camera is connected')
                else:
                    self._logger.log(Logger.LOG_LEVEL_WARN, 'No camera connected')
            source_file_path = result_dict[TetheringProcess.RESULT_KEY_SOURCE_PATH]
            if source_file_path is not None:
                self._logger.log(Logger.LOG_LEVEL_INFO, 'New file "{0}" on camera'.format(source_file_path))
            picture_name = result_dict[TetheringProcess.RESULT_KEY_PICTUE]
            if picture_name is not None:
                self._logger.log(Logger.LOG_LEVEL_INFO, 'Downloaded picture "{0}"'.format(picture_name))
                self.process_picture(picture_name)

    def run(self):
        run_in_demo_mode = self._config.get('RunInDemoMode')
        if run_in_demo_mode is True:
            self.run_in_demo_mode()
        else:
            self.run_in_productive_mode()


# Application Class

class Application:

    __INSTANCE = None

    @classmethod
    def first_instance(cls, config, logger):
        if cls.__INSTANCE is None:
            cls.__INSTANCE = Application(config, logger)
        return cls.__INSTANCE

    @classmethod
    def shared_instance(cls):
        return cls.__INSTANCE

    def __init__(self, config, logger):
        if self.__INSTANCE is not None:
            raise ValueError("An instantiation already exists!")
        # Set member variables
        self._config = config
        self._logger = logger
        self._sharedPhotoList = SharedPhotoList()
        self._sessionPath = self.create_capture_session_folder()
        self._hubList = None
        self._webserver = None
        self._zeroconfService = None
        self._teatherThread = None
        # Add allready existing photos to list
        photo_directory_path = os.path.join(self._sessionPath,
                                            self._config.get('PhotoFolder'))
        file_list = os.listdir(photo_directory_path)
        file_list.sort()
        for image_file_name in file_list:
            if image_file_name.endswith(".jpg"):
                self._sharedPhotoList.add_picture(image_file_name)

    def get_config(self):
        return self._config

    def get_logger(self):
        return self._logger

    def get_phared_photo_list(self):
        return self._sharedPhotoList

    def get_session_path(self):
        return self._sessionPath

    def get_hub_list(self):
        return self._hubList

    def create_capture_session_folder(self):
        folder = os.path.join(self._config.get('DataFolder'), self._config.get('SessionName'))
        if self._config.get('SessionName') == '':
            for i in range(1, 999):
                folder = os.path.join(self._config.get('DataFolder'), "capture_session_{0:02d}".format(i))
                if not (os.path.exists(folder)):
                    break
        thumbnail_path = os.path.os.path.join(folder, self._config.get('ThumbnailFolder'))
        photo_path = os.path.os.path.join(folder, self._config.get('PhotoFolder'))
        if not (os.path.exists(folder)):
            os.makedirs(folder)
            os.makedirs(thumbnail_path)
            os.makedirs(photo_path)
        return folder

    def run(self):
        self._logger.log(Logger.LOG_LEVEL_INFO, 'Application started')
        # Print Network information, if possible
        if self._config.get('RunInDemoMode') is False:
            try:
                for device in NetworkManager.NetworkManager.GetDevices():
                    address = device.Ip4Address
                    if (address != '0.0.0.0') and (address != '127.0.0.1'):
                        uri = 'http://{0}:{1}/index.html'.format(address, self._config.get('HttpPortNumber'))
                        print 'Interface "{0}": {1}'.format(device.Interface, uri)
                        try:
                            subprocess.call('qrencode -t UTF8 \'{0}\''.format(uri), shell=True)
                        except IOError:
                            pass
            except AttributeError:
                pass
        # Initialize Hub List
        self._hubList = HubList()
        # Publish Zero Conf service
        self._zeroconfService = ZeroconfService("Picture Streamer",
                                                int(self._config.get('HttpPortNumber')),
                                                text='application=PictureStreamer')
        self._zeroconfService.publish()
        # Start camera connection
        self._teatherThread = TetheringThread()
        self._teatherThread.start()
        # Start webserver
        self._webserver = ThreadingHttpServer(('', int(self._config.get('HttpPortNumber'))), PhotoStreamHttpHandler)
        ssl_cert_file_path = self._config.get('SSLCertPath')
        if ssl_cert_file_path != '' and os.path.isfile(ssl_cert_file_path):
            self._webserver.socket = ssl.wrap_socket(self._webserver.socket,
                                                     certfile=ssl_cert_file_path,
                                                     server_side=True)
        self._webserver.serve_forever()

    def exit(self):
        self._zeroconfService.unpublish()
        self._webserver.socket.close()
        self._logger.log(Logger.LOG_LEVEL_INFO, 'Application closed')

# Main function


def main(argv):
    config = Configuration()
    config.parse_arguments(argv)
    logger = Logger(config.get('LogFilePath'), config.get('RunAsDaemon'))
    app = None
    try:
        app = Application.first_instance(config, logger)
        app.run()
    except (KeyboardInterrupt, SystemExit):
        app.exit()

if __name__ == "__main__":
    main(sys.argv[1:])

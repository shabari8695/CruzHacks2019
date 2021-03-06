import argparse
import base64
from datetime import datetime
import os
import shutil

import numpy as np
import socketio
import eventlet
import eventlet.wsgi
from PIL import Image
from flask import Flask
from io import BytesIO
import datetime
import time
from keras.models import load_model
import h5py
from keras import __version__ as keras_version
import math
from numpy import genfromtxt
import grequests
import requests
from threading import Thread
#from sklearn.linear_model import LinearRegression
#from tf_model import get_model

sio = socketio.Server()
app = Flask(__name__)
model = None
prev_image_array = None
#reg = get_regression_model()

def get_displacement(l1,l2):
    sum = (l1[0]-l2[0])*(l1[0]-l2[0])
    return math.sqrt(sum)

def get_max(t1,t2):
    if t1 < t2:
        return 1
    else:
        return 0

def get_diff(t1,t2):
    diff = math.fabs(t1-t2)
    return diff

def get_z_dif(t1,t2):
    diff = math.fabs(t1[2]-t2[2])
    return diff

def get_best_dist(d):
    my_data = genfromtxt('regression.csv', delimiter=',')
    input_data = my_data[:,0]
    output_data = my_data[:,1]
    for i in range(input_data.shape[0]):
        if input_data[i] == d:
            return output_data[i]
    
    return 0.0

def make_call():
    #r = requests.post('http://169.233.112.37:3000/pay')
    #urls = ['http://127.0.0.1:3000/pay']
    urls = ['http://3.86.171.28:3000/pay']
    unsent_request = (grequests.post(url) for url in urls)
    results = grequests.map(unsent_request)
    for result in results:
        print(result.content)


def save_image(image,steering_angle):
    now = datetime.datetime.now()
    now = str(now.replace(microsecond=0)).replace(" ","_")
    file_path = "dAgger/IMG/"+now+".jpg"

    image.save(file_path,'JPEG')
    with open('dAgger/driving_log.csv','a') as f:
        f.write(file_path+","+str(steering_angle)+"\n")

class SimplePIController:
    def __init__(self, Kp, Ki):
        self.Kp = Kp
        self.Ki = Ki
        self.set_point = 0.
        self.error = 0.
        self.integral = 0.
        self.start_time = ""
        self.init_pos = ""
        self.sec = 1
        self.key_pressed = False
        self.first_frame = True

    def set_desired(self, desired):
        self.set_point = desired

    def update(self, measurement):
        # proportional error
        self.error = self.set_point - measurement

        # integral error
        self.integral += self.error

        return self.Kp * self.error + self.Ki * self.integral


controller = SimplePIController(0.1, 0.002)
set_speed = 9.0
epsilon = 0.75
controller.set_desired(set_speed)

@sio.on('telemetry')
def telemetry(sid, data):
    dAgger_update = False
    dist = 0.0
    actual = 0
    if data:
        pos = data["position"].replace("(","").replace(")","").replace(",","").split(" ")
        pos = [float(i) for i in pos]
        #print(pos)
        if controller.first_frame:
            controller.init_pos = pos
            controller.start_time = time.time()
            controller.first_frame = False
        else:
            curr = time.time()
            time_diff = curr - controller.start_time
            if time_diff >= 1:
                dist = get_displacement(controller.init_pos,pos)
                actual_dist = get_best_dist(controller.sec)
                #print(actual_dist)
                #print(dist)
                #with open('regression_better.csv','a') as f:
                    #f.write(str(controller.sec)+","+str(dist)+"\n")
                
                print(get_z_dif(controller.init_pos,pos))

                if get_max(actual_dist,dist) == 1 and np.random.uniform(0,1) > epsilon:
                    print("Model Improved! Sending Micropayment")
                    threaded = Thread(target = make_call,args = (),daemon=True)
                    threaded.start()
                elif get_diff(actual_dist,dist) > 2.0 :#get_z_dif(controller.init_pos,pos):
                    print(get_diff(actual_dist,dist))
                    print("Negative Reinforcement! Receiving Micropayment")
                    
                controller.sec +=1
                controller.init_pos = pos
                controller.start_time = curr
             

        if data["key_press"] in ["0","2"]:
            dAgger_update = True

        #print(pos)

        # The current steering angle of the car
        steering_angle = float(data["steering_angle"])
        # The current throttle of the car
        throttle = data["throttle"]
        # The current speed of the car
        speed = float(data["speed"])
        #print(speed)
        # The current image from the center camera of the car
        imgString = data["image"]
        image = Image.open(BytesIO(base64.b64decode(imgString)))
        image_array = np.asarray(image)

        if dAgger_update:
            if data["key_press"] == "0":
                if steering_angle >= 0:
                    steering_angle = -1*steering_angle
                steering_angle += -0.05
            elif data["key_press"] == "2":
                if steering_angle <= 0:
                    steering_angle = -1 * steering_angle
                steering_angle += 0.05

            save_image(image,steering_angle)
        else:
            steering_angle = float(model.predict(image_array[None, :, :, :], batch_size=1))
        
        throttle = controller.update(speed)

        #print(steering_angle, throttle)

        send_control(steering_angle, throttle)

    else:
        # NOTE: DON'T EDIT THIS.
        sio.emit('manual', data={}, skip_sid=True)


@sio.on('connect')
def connect(sid, environ):
    print("connect ", sid)
    send_control(0, 0)


def send_control(steering_angle, throttle):
    sio.emit(
        "steer",
        data={
            'steering_angle': steering_angle.__str__(),
            'throttle': throttle.__str__()
        },
        skip_sid=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Remote Driving')
    parser.add_argument(
        'model',
        type=str,
        help='Path to model h5 file. Model should be on the same path.'
    )
    parser.add_argument(
        'image_folder',
        type=str,
        nargs='?',
        default='',
        help='Path to image folder. This is where the images from the run will be saved.'
    )
    args = parser.parse_args()

    # check that model Keras version is same as local Keras version
    #f = h5py.File(args.model, mode='r')
    #model_version = f.attrs.get('keras_version')
    #keras_version = str(keras_version).encode('utf8')

    #if model_version != keras_version:
        #print('You are using Keras version ', keras_version,
              #', but the model was built using ', model_version)

    model = load_model(args.model)

    if args.image_folder != '':
        print("Creating image folder at {}".format(args.image_folder))
        if not os.path.exists(args.image_folder):
            os.makedirs(args.image_folder)
        else:
            shutil.rmtree(args.image_folder)
            os.makedirs(args.image_folder)
        print("RECORDING THIS RUN ...")
    else:
        print("NOT RECORDING THIS RUN ...")

    # wrap Flask application with engineio's middleware
    app = socketio.Middleware(sio, app)

    # deploy as an eventlet WSGI server
    eventlet.wsgi.server(eventlet.listen(('', 4567)), app)

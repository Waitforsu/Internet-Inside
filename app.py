from flask import Flask, render_template, request
import subprocess
import threading
import os
import signal

app = Flask(__name__)

# Global variable to keep track of the process
client_process = None

# Speed test function
def iperf_speed_test():
    result = subprocess.run(["iperf3", "-c", "192.168.1.2", "-p", "25001", "-u", "-b", "400K", "-t", "10", "-R"], capture_output=True, text=True)
    return result.stdout

# Function to start the client main program
def start_client_program():
    global client_process
    client_process = subprocess.Popen(["sudo", "/home/yaoi/myen/bin/python3", "mobile.py"])

# Function to stop the client main program
def stop_client_program():
    global client_process
    if client_process:
        os.kill(client_process.pid, signal.SIGTERM)
        client_process = None

# Ping function
def ping_target(target):
    try:
        result = subprocess.run(["ping", "-c", "4", "-I", "tun0", target], capture_output=True, text=True)
        return result.stdout
    except Exception as e:
        return str(e)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_mobile', methods=['POST'])
def start_mobile():
    threading.Thread(target=start_client_program).start()
    return render_template('index.html', mobile_started=True)

@app.route('/stop_mobile', methods=['POST'])
def stop_mobile():
    stop_client_program()
    return render_template('index.html', mobile_stopped=True)

@app.route('/start_speed_test', methods=['POST'])
def start_speed_test():
    speed_test_result = iperf_speed_test()
    return render_template('index.html', speed_test_result=speed_test_result)

@app.route('/ping', methods=['POST'])
def ping():
    target = request.form['target']
    ping_result = ping_target(target)
    return render_template('index.html', ping_result=ping_result)

if __name__ == '__main__':
    app.run(debug=True)

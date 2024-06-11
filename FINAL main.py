# how to import picozero https://projects.raspberrypi.org/en/projects/get-started-pico-w/1
from picozero import pico_temp_sensor, pico_led
import network
import socket
import machine
import utime
from time import sleep, localtime
from machine import Pin, ADC
import gc
import json

# Wi-Fi credentials
ssid = 'VM5792329'
password = 'rk2dqJpcGyjd'

# Set up the analog pin for the moisture sensor
moisture_pin = ADC(26)

# Set up the GPIO pin for the pump control
pump_pin = Pin(16, Pin.OUT)

# Calibration values (replace with your actual values)
dry_value = 43000
wet_value = 50000

# Initialize storage for historical data
data_points = []
pump_log = []
start_time = utime.time()

# Default moisture threshold for the pump
moisture_threshold = 30.0

# Global variable to keep track of pump state
pump_state = False

# Global variable for software watchdog
last_check_time = utime.time()
watchdog_timeout = 180  # 180-second timeout period

# Maximum pump activation time and cooldown
max_pump_time = 60  # 60 seconds
cooldown_time = 30  # 30 seconds
last_pump_activation = 0
last_pump_deactivation = 0  # Track the time when the pump was last deactivated

# Flag to track if cooldown is active
cooldown_active = False

# Function to read moisture level
def read_moisture():
    moisture_value = moisture_pin.read_u16()
    inverted_moisture = 65535 - moisture_value
    moisture_percentage = ((inverted_moisture - dry_value) / (wet_value - dry_value)) * 100
    moisture_percentage = max(0, min(moisture_percentage, 100))
    return moisture_percentage

# Function to activate the pump
def activate_pump():
    global pump_state
    global last_pump_activation
    if not pump_state:
        pump_pin.on()
        pump_state = True
        last_pump_activation = utime.time()
        pump_log.append(f"Pump Activated ({localtime_to_string(localtime())} for 0 seconds)")  # Initialize with 0 seconds
        if len(pump_log) > 10:  # Limit the pump log to 10 entries
            pump_log.pop(0)
        print("Pump activated")

# Function to deactivate the pump
def deactivate_pump():
    global pump_state
    global cooldown_active
    global last_pump_activation
    global last_pump_deactivation
    if pump_state:
        pump_pin.off()
        pump_state = False
        duration = int(utime.time() - last_pump_activation)
        pump_log[-1] = pump_log[-1].replace("0 seconds", f"{duration} seconds")
        cooldown_active = True  # Start cooldown period
        last_pump_deactivation = utime.time()
        print("Pump deactivated")

# Function to convert localtime to string
def localtime_to_string(time_tuple):
    return "{:02}/{:02}/{} at {:02}:{:02}:{:02}".format(time_tuple[2], time_tuple[1], time_tuple[0], time_tuple[3], time_tuple[4], time_tuple[5])

# Function to connect to the Wi-Fi network
def connect():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)
    while not wlan.isconnected():
        print('Waiting for connection...')
        sleep(3)
    ip = wlan.ifconfig()[0]
    print(f'Connected on {ip}')
    return ip

# Function to open a socket for HTTP communication
def open_socket(ip):
    address = (ip, 80)
    connection = socket.socket()
    connection.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    connection.bind(address)
    connection.listen(1)
    return connection

# Function to generate the HTML webpage
def webpage(temperature, state, moisture, auto_water, data_points, threshold):
    auto_water_status = "ON" if not auto_water else "OFF"
    data_json = json.dumps(data_points)
    led_color = "lightgreen" if state == "ON" else "darkgrey"
    temperature_color = "black"
    if temperature > 30:
        temperature_color = "#ff6666"  # pastel red
    elif temperature < 5:
        temperature_color = "#6666ff"  # pastel blue

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Auto Watering System</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: 'Avenir Next LT Pro', sans-serif;
                background-color: #1affd1;
                color: #000;
                margin: 0;
                padding: 0;
                text-align: left;
                padding-left: 10px;
            }}
            h1, p {{
                color: #000;
            }}
            h1, #temperature {{
                margin-left: 10px;
            }}
            .control-box {{
                border: 3px solid #000;
                padding: 10px;
                margin: 10px 0;
                text-align: center;
                width: 90%;
                max-width: 400px;
                box-sizing: border-box;
            }}
            .control-title {{
                font-weight: bold;
                text-align: center;
                margin-bottom: 10px;
            }}
            .inline-buttons {{
                display: flex;
                justify-content: center;
                align-items: center;
            }}
            .chart-container {{
                width: 90%;
                max-width: 600px;
                margin: 0;
            }}
            .led-status {{
                display: inline-block;
                width: 20px;
                height: 20px;
                background-color: {led_color};
                border-radius: 50%;
                margin-right: 10px;
            }}
            #temperature {{
                color: {temperature_color};
                font-size: 1.5em;
                margin-bottom: 10px;
            }}
            .pump-log {{
                margin-top: 20px;
            }}
        </style>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script>
            var dataPoints = {data_json};
            var chart;
            var moistureThreshold = {threshold};

            function refreshData() {{
                var xhr = new XMLHttpRequest();
                xhr.open('GET', '/data', true);
                xhr.onload = function() {{
                    if (xhr.status == 200) {{
                        var data = JSON.parse(xhr.responseText);
                        var temperatureElement = document.getElementById('temperature');
                        temperatureElement.innerHTML = data.temperature + ' &deg;C';
                        if (data.temperature > 30) {{
                            temperatureElement.style.color = '#ff6666'; // pastel red
                        }} else if (data.temperature < 5) {{
                            temperatureElement.style.color = '#6666ff'; // pastel blue
                        }} else {{
                            temperatureElement.style.color = 'black';
                        }}
                        document.getElementById('moisture').innerHTML = data.moisture + '%';
                        // Add new data point
                        var currentTime = new Date().toLocaleTimeString('en-GB', {{ hour12: false }});
                        dataPoints.push({{time: currentTime, temperature: data.temperature, moisture: data.moisture}});
                        // Keep only the last 1440 data points (1 day)
                        if (dataPoints.length > 1440) dataPoints.shift();
                        updateChart();
                    }}
                }};
                xhr.send();
            }}

            function refreshPumpLog() {{
                var xhr = new XMLHttpRequest();
                xhr.open('GET', '/pumplog', true);
                xhr.onload = function() {{
                    if (xhr.status == 200) {{
                        var pumpLogElement = document.getElementById('pump-log-entries');
                        pumpLogElement.innerHTML = xhr.responseText;
                    }}
                }};
                xhr.send();
            }}

            function controlLED(action) {{
                var xhr = new XMLHttpRequest();
                xhr.open('GET', '/' + action, true);
                xhr.onload = function() {{
                    if (xhr.status == 200) {{
                        console.log(action + ' action completed');
                        var ledCircle = document.getElementById('led-status');
                        ledCircle.style.backgroundColor = (action === 'lighton') ? 'lightgreen' : 'darkgrey';
                    }}
                }};
                xhr.send();
            }}

            function controlPump(action) {{
                var xhr = new XMLHttpRequest();
                xhr.open('GET', '/pump?action=' + action, true);
                xhr.onload = function() {{
                    if (xhr.status == 200) {{
                        console.log('Pump ' + action + ' action completed');
                        document.getElementById('auto-water-status').innerHTML = 'OFF';
                        refreshPumpLog();
                    }}
                }};
                xhr.send();
            }}

            function autowaterControl() {{
                var xhr = new XMLHttpRequest();
                xhr.open('GET', '/autowater', true);
                xhr.onload = function() {{
                    if (xhr.status == 200) {{
                        console.log('Autowater action completed');
                        document.getElementById('auto-water-status').innerHTML = 'ON';
                    }}
                }};
                xhr.send();
            }}

            function updateThreshold() {{
                var thresholdInput = document.getElementById('threshold-input').value;
                if (thresholdInput && !isNaN(thresholdInput) && thresholdInput >= 0 && thresholdInput <= 100) {{
                    moistureThreshold = parseFloat(thresholdInput);
                    var xhr = new XMLHttpRequest();
                    xhr.open('GET', '/threshold?value=' + moistureThreshold, true);
                    xhr.onload = function() {{
                        if (xhr.status == 200) {{
                            console.log('Threshold updated');
                            updateChart();
                        }}
                    }};
                    xhr.send();
                }} else {{
                    alert('Please enter a valid number between 0 and 100.');
                }}
            }}

            function initializeChart() {{
                var ctx = document.getElementById('chart').getContext('2d');
                chart = new Chart(ctx, {{
                    type: 'line',
                    data: {{
                        labels: dataPoints.map(dp => dp.time),
                        datasets: [
                            {{
                                label: 'Temperature',
                                data: dataPoints.map(dp => dp.temperature),
                                borderColor: 'rgba(255, 99, 132, 0.6)', // Pastel red
                                backgroundColor: 'rgba(255, 99, 132, 0.2)', // Pastel red fill
                                borderWidth: 1,
                                fill: false,
                                pointStyle: 'circle'
                            }},
                            {{
                                label: 'Moisture (%)',
                                data: dataPoints.map(dp => dp.moisture),
                                borderColor: 'rgba(54, 162, 235, 0.6)', // Pastel blue
                                backgroundColor: 'rgba(54, 162, 235, 0.2)', // Pastel blue fill
                                borderWidth: 1,
                                fill: false,
                                pointStyle: 'circle'
                            }},
                            {{
                                label: 'Pump Threshold',
                                data: dataPoints.map(dp => moistureThreshold),
                                borderColor: 'rgba(75, 75, 75, 1)', // Dark grey
                                borderWidth: 2,
                                borderDash: [5, 5],
                                fill: false,
                                pointRadius: 0,
                                pointStyle: 'line'
                            }}
                        ]
                    }},
                    options: {{
                        scales: {{
                            x: {{
                                type: 'category',
                                title: {{
                                    display: true,
                                    text: 'Time'
                                }}
                            }},
                            y: {{
                                beginAtZero: true,
                                min: 0,
                                max: 100,
                                title: {{
                                    display: true,
                                    text: 'Value'
                                }}
                            }}
                        }},
                        plugins: {{
                            legend: {{
                                labels: {{
                                    usePointStyle: true
                                }}
                            }}
                        }}
                    }}
                }});
            }}

            function updateChart() {{
                chart.data.labels = dataPoints.map(dp => dp.time);
                chart.data.datasets[0].data = dataPoints.map(dp => dp.temperature);
                chart.data.datasets[1].data = dataPoints.map(dp => dp.moisture);
                chart.data.datasets[2].data = dataPoints.map(dp => moistureThreshold);
                chart.update();
            }}

            window.onload = function() {{
                initializeChart(); // Initialize chart on page load
                refreshData(); // Load initial data
                refreshPumpLog(); // Load initial pump log
                setInterval(refreshData, 5000); // Refresh data every 5 seconds
                setInterval(refreshPumpLog, 5000); // Refresh pump log every 5 seconds
                document.getElementById('threshold-input').addEventListener('change', updateThreshold);
            }};
        </script>
    </head>
    <body>
        <h1>Auto Watering System</h1>
        <p id="temperature">{temperature:.1f} &deg;C</p>
        <div class="control-box">
            <div class="control-title">LED</div>
            <div class="inline-buttons">
                <span id="led-status" class="led-status"></span>
                <button onclick="controlLED('lighton')">Light on</button>
                <button onclick="controlLED('lightoff')">Light off</button>
            </div>
        </div>
        <div class="control-box">
            <div class="control-title">Pump Control</div>
            <div class="inline-buttons">
                <button onclick="controlPump('on')">Pump On</button>
                <button onclick="controlPump('off')">Pump Off</button>
                <button onclick="autowaterControl()">Autowater</button>
            </div>
        </div>
        <p>Moisture Level: <span id="moisture">{moisture:.2f}%</span></p>
        <p>Moisture Threshold (for Pump): <input type="text" id="threshold-input" value="{threshold}" size="3" /> %</p>
        <p>Automatic Watering is <span id="auto-water-status">{auto_water_status}</span></p>
        <div class="chart-container">
            <canvas id="chart"></canvas>
        </div>
        <div class="pump-log" id="pump-log">
            <h2>Pump Activation Log</h2>
            <div id="pump-log-entries"></div>
        </div>
    </body>
    </html>
    """
    return str(html)

# Function to handle different request paths
def handle_request(request_path):
    global pump_control_override
    global last_temperature_update
    global moisture_threshold

    if request_path.startswith('/lighton'):
        pico_led.on()
        return '200 OK', None
    if request_path.startswith('/lightoff'):
        pico_led.off()
        return '200 OK', None
    if request_path.startswith('/pump?action=on'):
        pump_control_override = True
        activate_pump()
        return '200 OK', None
    if request_path.startswith('/pump?action=off'):
        pump_control_override = True
        deactivate_pump()
        return '200 OK', None
    if request_path.startswith('/autowater'):
        pump_control_override = False
        print("Autowater activated. Automatic control re-enabled.")
        return '200 OK', None
    if request_path.startswith('/threshold'):
        threshold_value = request_path.split('=')[1]
        if threshold_value and not threshold_value.isspace():
            try:
                moisture_threshold = float(threshold_value)
                return '200 OK', None
            except ValueError:
                return '400 Bad Request', 'Invalid threshold value'
    if request_path.startswith('/data'):
        moisture = read_moisture()
        current_time = utime.time()
        if current_time - last_temperature_update >= 30:
            temperature = pico_temp_sensor.temp
            last_temperature_update = current_time
        else:
            temperature = pico_temp_sensor.temp
        response = '{{"temperature": {:.1f}, "moisture": {:.2f}}}'.format(temperature, moisture)
        return '200 OK', response
    if request_path.startswith('/pumplog'):
        pump_log_html = "".join([f"<p>{entry}</p>" for entry in pump_log])
        return '200 OK', pump_log_html

    return '404 Not Found', '<h1>404 Not Found</h1>'

# Initialize the system
def initialize_system():
    global pump_control_override
    global last_temperature_update
    global start_time
    pump_control_override = False
    last_temperature_update = utime.time()
    start_time = utime.time()
    ip = connect()
    connection = open_socket(ip)
    return connection

# Main loop
def main():
    global last_check_time
    global last_pump_activation
    global cooldown_active
    global last_pump_deactivation
    connection = initialize_system()
    state = 'OFF'
    auto_water = False

    while True:
        try:
            current_time = utime.time()
            
            client, addr = connection.accept()
            request = client.recv(1024)
            request = request.decode('utf-8')
            request_path = request.split(' ')[1]

            if request_path != '/data' and request_path != '/pumplog':
                print(f'Request Path: {request_path}')

            status, response = handle_request(request_path)
            moisture = read_moisture()
            temperature = pico_temp_sensor.temp

            if current_time - start_time <= 60:
                data_interval = 5  # First 60 seconds: collect data every 5 seconds
            else:
                data_interval = 60  # After 60 seconds: collect data every minute

            if (current_time - start_time) % data_interval == 0:
                # Add new data point
                time_tuple = localtime()
                formatted_time = "{:02}:{:02}:{:02}".format(time_tuple[3], time_tuple[4], time_tuple[5])
                data_points.append({"time": formatted_time, "temperature": temperature, "moisture": moisture})
                if len(data_points) > 1440:  # Keep only the last 1440 data points (1 day)
                    data_points.pop(0)

            if not pump_control_override:
                if moisture < moisture_threshold and not cooldown_active:
                    if not pump_state:
                        activate_pump()
                    elif pump_state and (current_time - last_pump_activation >= max_pump_time):
                        deactivate_pump()
                elif moisture >= moisture_threshold:
                    if pump_state:
                        deactivate_pump()

            # Check if cooldown period has passed
            if cooldown_active and (current_time - last_pump_deactivation >= cooldown_time):
                cooldown_active = False

            if request_path == '/data' or request_path == '/pumplog':
                client.send(f'HTTP/1.1 {status}\r\n')
                client.send('Content-Type: text/html\r\n')
                client.send('Connection: close\r\n\r\n')
                client.sendall(response.encode('utf-8'))
            else:
                response = webpage(temperature, state, moisture, auto_water, data_points, moisture_threshold)
                client.send(f'HTTP/1.1 {status}\r\n')
                client.send('Content-Type: text/html\r\n')
                client.send('Connection: close\r\n\r\n')
                client.sendall(response.encode('utf-8'))
            client.close()

            # Ensure pump doesn't run longer than max_pump_time in auto mode
            if not pump_control_override and pump_state and (current_time - last_pump_activation >= max_pump_time):
                deactivate_pump()

            # Software watchdog check and reset
            if current_time - last_check_time > watchdog_timeout:
                print("Software watchdog reset")
                machine.reset()
            last_check_time = current_time  # Move this to ensure it's always updated after main operations

            # Force garbage collection to free memory
            gc.collect()

        except Exception as e:
            print(f'An error occurred: {e}')
            machine.reset()  # Reset the Pico on exception

# Run the main loop
main()


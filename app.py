from flask import Flask, request, jsonify, render_template, redirect, url_for
from helper.ip import get_local_ip
from helper.kasa_helper import KasaHelper
from datetime import datetime
from helper.scheduler import create_scheduler


app = Flask(__name__)

sensor_data = {}
ip = get_local_ip()

automation_rules = []
scheduled_tasks = []

scheduler = create_scheduler('US/Eastern')
scheduler.start()

led_state = {'status': 0, 'color': '#FFFFFF'}
curr_profile = {}
profiles = []

# for smart plug
kasa = KasaHelper()
kasa.discover_plugs()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/devices')
def devices():
    plug_states = kasa.get_all_plug_states()
    return render_template('devices.html', server_ip=ip, sensor_data=sensor_data, plugs=plug_states, automation_rules=automation_rules, scheduled_tasks=scheduled_tasks)


@app.route('/led_control')
def led_control():
    return render_template('led.html', sensor_data=sensor_data, profiles=profiles, curr_profile=curr_profile)


@app.route('/led_switch', methods=['POST'])
def led_switch():
    state = request.form.get('status')
    if state == 'on':
        led_state['status'] = 1
    elif state == 'off':
        led_state['status'] = 0
    else:
        return "Invalid input", 400
    
    return redirect(url_for('led_control'))


@app.route('/submit_profile', methods=['GET', 'POST'])
def submit_profile():
    if request.method == 'POST':
        # Get form data
        profile_name = request.form.get('profile_name')
        sensor_id = request.form.get('device_id')
        reading = request.form.get('reading')

        # Extract ranges
        min_values = request.form.getlist('min[]')
        max_values = request.form.getlist('max[]')
        color_values = request.form.getlist('color[]')

        # Validate required fields
        if not profile_name or not sensor_id or not reading or not min_values:
            return "Invalid data received", 400

        # Build ranges
        ranges = []
        for min_val, max_val, color in zip(min_values, max_values, color_values):
            ranges.append({
                "min": float(min_val) if min_val else None,
                "max": float(max_val) if max_val else None,
                "color": color
            })

        # Add new profile to profiles list
        new_profile = {
            "profile_name": profile_name,
            "sensor_id": sensor_id,
            "reading": reading,
            "ranges": ranges
        }
        profiles.append(new_profile)

        # Redirect to a control page or refresh the current page
        return redirect(url_for('led_control'))

    return redirect(url_for('led_control'))


@app.route('/update_profile', methods=['POST'])
def update_profile():
    global curr_profile
    selected_profile_name = request.form.get('profile_name')
    for profile in profiles:
        if profile['profile_name'] == selected_profile_name:
            curr_profile = profile
            break
    return redirect(url_for('led_control'))



@app.route('/delete_profile', methods=['POST'])
def delete_profile():
    global profiles, curr_profile

    profile_name = request.form.get('profile_name')

    # Remove the profile from the profiles list
    profiles = [profile for profile in profiles if profile['profile_name'] != profile_name]

    # If the deleted profile is the current profile, reset curr_profile
    if curr_profile and curr_profile['profile_name'] == profile_name:
        curr_profile = {}

    # Redirect to the main page
    return redirect(url_for('led_control'))


@app.route('/led_state', methods=['GET'])
def get_led_state():
    return jsonify(led_state)


@app.route('/on/<path:ip>')
def turn_on(ip):
    kasa.turn_on_plug(ip)
    return redirect(url_for('devices'))


@app.route('/off/<path:ip>')
def turn_off(ip):
    kasa.turn_off_plug(ip)
    return redirect(url_for('devices'))


@app.route('/rename/<path:ip>', methods=['POST'])
def rename(ip):
    new_alias = request.form.get('new_alias')
    if new_alias:
        kasa.rename_plug(ip, new_alias)
    return redirect(url_for('devices'))


@app.route('/data', methods=['GET'])
def get_sensor_data():
    return jsonify(sensor_data)


@app.route('/data', methods=['POST'])
def receive_data():
    """
    Endpoint for Pico W devices to report sensor data.
    Example Payload:
    {
        "device_id": "sensor_1",
        "readings": {
            "temperature": 20,
            "humidity": 10
        }
    }
    """
    data = request.json
    device_id = data.get('device_id')
    readings = data.get('readings')  # This should be a dictionary of readings

    if device_id and isinstance(readings, dict):
        # Update the datastore with readings for this device
        if device_id not in sensor_data:
            sensor_data[device_id] = {}
        sensor_data[device_id].update(readings)
        
        print(device_id, sensor_data[device_id])
        check_automation_rules(device_id, sensor_data[device_id])
        determine_color(device_id, readings)  # Determine LED color based on the profile
        return jsonify({'status': 'success'}), 200

    return jsonify({'status': 'error', 'message': 'Invalid data'}), 400


@app.route('/add_rule', methods=['POST'])
def add_rule():
    device_id = request.form.get('device_id')
    reading = request.form.get('reading')
    operator = request.form.get('operator')
    threshold = request.form.get('threshold', type=float)
    plug_ip = request.form.get('plug_ip')
    action = request.form.get('action')

    if device_id and reading and operator and threshold is not None and action and plug_ip:
        rule = {
            "device_id": device_id,
            "reading": reading,
            "operator": operator,
            "threshold": threshold,
            "plug_ip": plug_ip,
            "action": action
        }
        automation_rules.append(rule)
        return redirect(url_for('devices'))
    else:
        return jsonify({'status': 'error', 'message': 'Invalid rule data'}), 400
    

@app.route('/delete_rule/<int:rule_index>', methods=['POST'])
def delete_rule(rule_index):
    if 0 <= rule_index < len(automation_rules):
        deleted_rule = automation_rules.pop(rule_index)
        return redirect(url_for('devices'))
    else:
        return jsonify({'status': 'error', 'message': 'Invalid rule index'}), 400


@app.route('/add_schedule', methods=['POST'])
def add_schedule():
    """Add a scheduled action for a specific future time."""
    plug_ip = request.form.get('plug_ip')
    action = request.form.get('action')
    scheduled_time_str = request.form.get('scheduled_time')

    if not (plug_ip and action and scheduled_time_str):
        return jsonify({'status': 'error', 'message': 'Missing data'}), 400

    # Parse the scheduled time
    try:
        run_time = datetime.strptime(scheduled_time_str, '%Y-%m-%d %H:%M')
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid datetime format. Use YYYY-MM-DD HH:MM'}), 400

    # Add a job to the scheduler
    job = scheduler.add_job(
        func=perform_scheduled_action,
        trigger='date',
        run_date=run_time,
        args=[plug_ip, action]
    )

    scheduled_tasks.append({
        'job_id': job.id,
        'plug_ip': plug_ip,
        'action': action,
        'run_time': run_time.strftime('%Y-%m-%d %H:%M')
    })

    return redirect(url_for('devices'))


@app.route('/delete_schedule/<job_id>', methods=['POST'])
def delete_schedule(job_id):
    """Delete a scheduled job."""
    try:
        scheduler.remove_job(job_id)
    except:
        pass  # Job may have already run or doesn't exist
    # Remove from scheduled_tasks list
    for i, task in enumerate(scheduled_tasks):
        if task['job_id'] == job_id:
            scheduled_tasks.pop(i)
            break
    return redirect(url_for('devices'))


def evaluate_condition(sensor_value, operator, threshold):
    if operator == '>':
        return sensor_value > threshold
    elif operator == '<':
        return sensor_value < threshold
    elif operator == '=':
        return sensor_value == threshold
    return False


def perform_scheduled_action(plug_ip, action):
    """This function is called by the scheduler at the scheduled time."""
    print(f"Performing scheduled action: {action} on {plug_ip}")
    plug_states = kasa.get_all_plug_states()
    current_state = plug_states.get(plug_ip)
    if current_state:
        plug_is_on = current_state['is_on']
        # Only perform action if plug is not already in desired state
        if action == 'on' and not plug_is_on:
            kasa.turn_on_plug(plug_ip)
        elif action == 'off' and plug_is_on:
            kasa.turn_off_plug(plug_ip)


def check_automation_rules(device_id, readings):
    plug_states = kasa.get_all_plug_states()  # Update and get current states
    for rule_index, rule in enumerate(automation_rules):
        if rule['device_id'] == device_id:
            sensor_value = readings.get(rule['reading'])
            if sensor_value is not None and evaluate_condition(sensor_value, rule['operator'], rule['threshold']):
                # Condition met - decide what to do with the target plug
                target_plug_ip = rule.get('plug_ip')
                action = rule.get('action')
                
                if target_plug_ip and action in ["on", "off"]:
                    current_state = plug_states.get(target_plug_ip)
                    if current_state:
                        plug_is_on = current_state['is_on']
                        
                        # If action is turn_on and plug is currently off -> turn on
                        if action == "on" and not plug_is_on:
                            print(f"Triggering action for rule {rule_index}: Turning on {target_plug_ip}")
                            kasa.turn_on_plug(target_plug_ip)
                        
                        # If action is turn_off and plug is currently on -> turn off
                        elif action == "off" and plug_is_on:
                            print(f"Triggering action for rule {rule_index}: Turning off {target_plug_ip}")
                            kasa.turn_off_plug(target_plug_ip)
                        # Otherwise, do nothing if the plug is already in the desired state.



def determine_color(device_id, readings):
    """
    Determines the LED color based on the current profile and updates led_state's color.
    The on/off status is handled separately.
    """
    global curr_profile, led_state

    if not curr_profile:
        return

    # Check if the device_id matches the current profile's sensor_id
    if curr_profile['sensor_id'] != device_id:
        return

    # Get the reading type from the profile
    reading_type = curr_profile['reading']
    reading_value = readings.get(reading_type)

    if reading_value is None:
        return

    # Determine the color based on the ranges in the current profile
    for range_item in curr_profile['ranges']:
        min_value = range_item.get('min', None)
        max_value = range_item.get('max', None)

        # Check if the reading falls within the range
        if (min_value is None or reading_value >= min_value) and (max_value is None or reading_value <= max_value):
            led_state['color'] = range_item['color']  # Update only the color
            print(f"Updated LED color to {range_item['color']} for reading {reading_value}.")
            return

    # If no range matches, no change to led_state
    print(f"No matching range found for reading {reading_value}. LED color remains {led_state['color']}.")



if __name__ == '__main__':
    # Set host to '0.0.0.0' to make the server accessible externally
    app.run(host='0.0.0.0', port=5000, debug=True)

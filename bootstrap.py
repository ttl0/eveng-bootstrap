#!/usr/bin/env python3
import time
import re
from netmiko import ConnectHandler
from evengsdk.client import EvengClient
from threading import Thread

def nxos_provision(host, port, tbr, commands, hostname):
    '''
    Provision nxos device using telnet for eve-ng.
    host: IP address of the EVE-NG server 
    port: Telnet port given to the device
    tbr: Time Between Requests is how long to sleep
    between commands.
    commands: List of strings that are commands for
    the device.
    '''
    console = {
            'device_type': 'generic_termserver_telnet',
            'ip': host,
            'port': port 
        }
    net_connect = ConnectHandler(**console)
    loading_stage1 = True
    loading_stage2 = True
    loading_stage3 = True

    # We wait for the device to present us with the
    # option to skip POAP - Power On Auto Provisioning
    print("{} - Stage 0 - Waiting for device to boot".format(hostname)) 
    while loading_stage1:
        output = net_connect.read_channel()
        if 'skip' in output:
            net_connect.write_channel('skip\r')
            loading_stage1 = False
        elif 'loader >' in output:
            net_connect.write_channel('boot nxos.9.2.2.bin\r')
        elif 'switch#' in output or 'config)#' in output or 'login:' in output:
            loading_stage1 = False
        time.sleep(tbr)
        net_connect.write_channel('\r')

    print("{} - Stage 1 - Device booted and SOAP skipped".format(hostname))

    # We wait for the login prompt to appear so we can
    # log into the device. Default credentials for N9K
    # is username 'admin' and no password
    while loading_stage2:
        output = net_connect.read_channel()
        if 'login:' in output:
            net_connect.write_channel('admin\r')
            time.sleep(tbr)
            net_connect.write_channel('\r')
            loading_stage2 = False
        elif '#' in output:
            loading_stage2 = False
        time.sleep(tbr)
    print("{} - Stage 2 - Logged in device. Sending commands".format(hostname))

    # We wait for the login process to complete and then
    # iterate over all the commands provided and send them
    # one by one.
    while loading_stage3:
        output = net_connect.read_channel()
        net_connect.write_channel('\r')
        if 'switch#' in output:
            for command in commands:
                net_connect.write_channel(command + '\r')
                time.sleep(tbr)
            loading_stage3 = False
        elif 'config)#' in output:
            loading_stage3 = False
        time.sleep(tbr)
    print("{} - Stage 3 - Device configured.".format(hostname))


def nxos_command(host, port, tbr, command):
    '''
    Takes a command as an argument runs the command and 
    returns the output of that command.
    '''
    console = {
            'device_type': 'generic_termserver_telnet',
            'ip': host,
            'port': port 
        }
    net_connect = ConnectHandler(**console)
    net_connect.write_channel(command+'\r')
    time.sleep(tbr)
    output = net_connect.read_channel()
    return output

def extract_ip(text):
    '''
    This function takes a string as an input and returns an IP address
    found in that string
    '''
    return re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', text).group() 

def mt_print(msg):
    with PRINT_LOCK:
        print(msg)

def run_mt(mt_function, q, **kwargs):
    num_threads = min(NUM_THREADS, len(BREAKOUT_PORTS))

    for i in range(num_threads):
        thread_name = f'Thread-{i}'
        worker = Thread(name=thread_name, target=mt_function, args=(q, kwargs))
        worker.start()
        
    q.join()    

if __name__ == "__main__":
    # Provide lab name and credentials to log in EVE-NG
    # Lab name as defined in the URL when created
    lab = 'Provision.unl'

    # IP Address of EVE-NG server
    eveng = '10.0.1.100'

    # Username to login EVE-NG server
    eveng_user = 'admin'

    # Password to login EVE-NG server
    eveng_password= 'eve'

    # We use an EVE-NG SDK to extract the Telnet ports of the devices
    # configured in the lab.

    # Instantiates EVE-NG SDK object to make API calls
    client = EvengClient(eveng)
    client.login(username=eveng_user, password=eveng_password)
    result = client.get('/labs/'+lab+'/nodes')
    
    # We create a dictionary that will store Key: Value as:
    # Key: Name of the device as defined in EVE-NG
    # Value: Telnet port of the device 
    devices = {}
    for data in result.items():
        if data[1]['template'] == 'nxosv9k':
            name = data[1]['name']
            url = data[1]['url'].split(':')[-1]
            # Have to add 128 for the port to match properly, not sure why
            devices[name] = str(url)

    print("The Following devices will be provisioned:")
    for hostname in devices:
        print(hostname)

    # Time Between Requests - how long to sleep between commands sent
    tbr = 1

    # Make sure all devices are booted ON or this loop will fail on devices
    # powered off
    for hostname, port in devices.items():
        commands = [
               'conf t', 'int mgmt0', 'vrf member management',
               'ip add dhcp', 'username admin password admin role priv-15',
               'hostname ' + hostname
               ]
        print("Starting thread for {} on port {}".format(hostname, port))

        thread = Thread(target = nxos_provision, args = (eveng, port, tbr,
            commands, hostname))
        thread.start()
        #nxos_provision(eveng, port, tbr, commands, hostname)

        # Sleep 10 seconds to make sure we get a DHCP address
    thread.join()

    print("Waiting for DHCP..")
    time.sleep(10)
    for hostname, port in devices.items():
        command = 'sh ip int b vrf management'
        output = nxos_command(eveng, port, tbr, command)
        try:
            ip = extract_ip(output)
            devices[hostname] = ip
            print("{} completed.".format(hostname))
        except:
            print("ERROR! {} could not get a DHCP address".format(hostname))

        # We rewrite our devices dictionary to store the IP address of
        # the device as Value instead of the port number as follows:
        # Key: Name of the device as defined in EVE-NG
        # Value: IP address of the device 

    # Creates a local file called "hosts" to use as an ansible inventory file
    with open("hosts", "a+") as f:
        for hostname, ip in devices.items():
            f.write("{}    ansible_host={}\n".format(hostname, ip))



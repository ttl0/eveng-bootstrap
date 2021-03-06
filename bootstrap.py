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


def send_command(host, port, tbr, command):
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
    try:
        return re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', text).group() 
    except:
        return "" 


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
    # Time the operation by starting a timer
    start_time = time.time()

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
    threads = []
    for hostname, port in devices.items():
        commands = [
               'conf t', 'int mgmt0', 'vrf member management',
               'ip add dhcp', 'username admin password admin role priv-15',
               'hostname ' + hostname
               ]
        print("Starting thread for {} on port {}".format(hostname, port))
        


        thread = Thread(target = nxos_provision, args = (eveng, port, tbr,
            commands, hostname))
        threads.append(thread)
        thread.start()

    # Wait for all threads to finish
    for x in threads:
        x.join()

    for hostname, port in devices.items():
        command = 'sh ip int b vrf management'
        
        # Try to get DHCP address for 60seconds
        timeout = 60
        tries = 0
        dhcpflag = False 
        print("{} - Checking for DHCP address...".format(hostname))
        while not dhcpflag: 
            output = send_command(eveng, port, tbr, command)
            ip = extract_ip(output)
            # We check if we are able to get an IP address
            if ip != "":
                dhcpflag = True

                # We rewrite our devices dictionary to store the IP address of
                # the device as Value instead of the port number as follows:
                # Key: Name of the device as defined in EVE-NG
                # Value: IP address of the device 
                devices[hostname] = ip
                print("{} completed.".format(hostname))

                # Creates a local file called "hosts" to use as an ansible inventory file
                with open("hosts", "w") as f:
                    for hostname, ip in devices.items():
                        f.write("{}    ansible_host={}\n".format(hostname, ip))

            # We sleep 1 second and increment the timer until we can get an
            # address
            elif tries < timeout:
                print("{} - Waiting for DHCP, will check again in 5 seconds...".format(hostname))
                tries += 5 
                time.sleep(5)
            # If we reach the timeout, we give up and continue to the next host
            elif tries == timeout:
                print("ERROR! {} could not get a DHCP address".format(hostname))
                dhcpflag = True

    print("Completed in {} seconds".format(time.time() - start_time))





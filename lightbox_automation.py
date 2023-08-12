from light_control import light_source
import time
import datetime
import os
import subprocess


'''
	Flicker-frequency: 0, 50, 60
	temp profiles: D50, D60
	lux values: 0-10;10-100;100-1000

	Test-matrix:
	0,5500,0-10; 0,5500,10-100: 0,5500,100-1000; reboot
	0,6500,0-10; 0,6500,10-100: 0,6500,100-1000; reboot

	50,5500,0-10; 50,5500,10-100: 50,5500,100-1000; reboot
	50,6500,0-10; 50,6500,10-100: 50,6500,100-1000; reboot

	60,5500,0-10; 60,5500,10-100: 60,5500,100-1000; reboot
	60,6500,0-10; 60,6500,10-100: 60,6500,100-1000; reboot

'''

dir_path = os.path.dirname(os.path.realpath(__file__))
app_path = os.path.join(dir_path, 'data_collection_tamper-detection-mac-FN-ONLY', 'tamper-detection.pex')
cmd_to_reboot_device = f"adb reboot"
exec_time_dict={} # dictionary to hold execution times at the end of execution of every option(test scenario)


def light_box():
    '''
        Initializes the light_source class
        Creates different options (or test scenarios), each option is a dictionary; creates a list of dictionaries.
    '''

    dict_setup = {
        "port" : "usbmodem206",
        "light_source" : "solbox"
    }
    light = light_source(**dict_setup) # create light source object

    options = []
    for flicker_freq in [0,50,60]:

        for temp in [5500, 6500]:

            for lum in range (0, 10, 1):
                dict_execute = {
                    "luminance" : lum/1000,
                    "cct" : temp,
                    "flicker_freq" : flicker_freq}
                options.append(dict_execute)

            for lum in range (10, 100, 10):
                dict_execute = {
                    "luminance" : lum/1000,
                    "cct" : temp,
                    "flicker_freq" : flicker_freq}
                options.append(dict_execute)

            for lum in range (100, 1001, 100):
                dict_execute = {
                    "luminance" : lum/1000,
                    "cct" : temp,
                    "flicker_freq" : flicker_freq}
                options.append(dict_execute)
        
    return light, options


def supernova_test(option, today, chromameter, capture_mode='SNAPSHOT'):
    '''
    for each option (test-scenario), execute the supernova test below

    '''

    luminance = int(option["luminance"]*1000)
    flicker_freq = option["flicker_freq"]
    temp = option["cct"]

    # if flicker frequency is 0, we are collecting 5 samples; for flicker frequency 50&60, we are collecting 30 samples
    if flicker_freq==0:
        if capture_mode in 'SNAPSHOT':
            cmd = f"python3 {app_path} -o results/{today}/{flicker_freq}Hz-{temp}K-{luminance}LUX-LM{chromameter}_{capture_mode}_MODE -c 2 -n 5" # change 2 to 5
        else:
            cmd = f"python3 {app_path} -o results/{today}/{flicker_freq}Hz-{temp}K-{luminance}LUX-LM{chromameter}_{capture_mode}_MODE -c 2 -n 5 -s live-streaming" # change 2 to 5
    elif flicker_freq in [50,60]:
        if capture_mode in 'SNAPSHOT':
            cmd = f"python3 {app_path} -o results/{today}/{flicker_freq}Hz-{temp}K-{luminance}LUX-LM{chromameter}_{capture_mode}_MODE -c 2 -n 30" # change 2 to 30
        else:
            cmd = f"python3 {app_path} -o results/{today}/{flicker_freq}Hz-{temp}K-{luminance}LUX-LM{chromameter}_{capture_mode}_MODE -c 2 -n 30 -s live-streaming" # change 2 to 30

    try:
        print(f'Starting Supernova test...')
        output = subprocess.check_output(cmd, shell=True)
    except Exception as e:
        print(e)
        raise Exception("Supernova test execution raised excpeiton during execution.")


#### Main Code ######

# Create your presets
light, options = light_box()
today = datetime.datetime.now().strftime("%Y%m%d_%H%M")
chromameter = light.get_avg_luminance()

print(today)
print(f'Chromameter readout: {chromameter}')
print(options)

#### Loop through all presets for SNAPSHOT mode ####
print("========= Start of SNAPSHOT-mode run ==========")

'''
    - get start_timer
    - set light conditions in the lightbox
    - get chromameter reading
    - execute supernova test
    - get end timer
    - update dictionary with exectuion time
    - after lux=1000; restrt the device
'''

for option in options:

    print("#### Start of individual run - snap #####")

    print(f"Option:{option}")

    start_time = time.time() # Start timer

    # Set the light conditions in the SOL box
    try:
        light.set_light(**option)
    except Exception as e:
        print(e)

        print("Sleep for 2 secs before retrying")
        time.sleep(2) # sleep for 2 secs before retrying it

        # there was exception, hence reTrying to set the light in the box for second time..
        print("There was exception, hence reTrying to set the light in the box for second time..")
        try:
            light.reconnect()
        except Exception as e:
            exec_time_dict[str(option)]="Exception in setting light env in sol box." 
            continue

        #TODO:
        #    restart lightbox; sleep 2 secs; update exec_dict; continue with next option
        #raise Exception("Exception in writing to sol box... serial port exception")

    print(f"Chromameter readout:{light.get_avg_luminance()}")

    msg=""
    try:
        supernova_test(option, today, chromameter)    # execute the tests for this given option
    except Exception as e:
        msg="Exception encountered while executing the test, may be timeout exception" 
        
    end_time = time.time() # End timer

    elapsed_time = end_time - start_time # Execution time

    if len(msg)==0:
        exec_time_dict[str(option)]=elapsed_time     # make an entry into the exec_time diectionary, execution time taken for executing this option
    else:
        exec_time_dict[str(option)]=msg              # if there is an exception during execution, login a message in the dictionary instead of execution time..

    # Rebooting the device on completion of one run of lux values from 0-1000
    if option['luminance'] == 1.0:
        try:
            #import pdb; pdb.set_trace()
            print(f'Rebooting the device at the end of run of lux from 0-1000')
            output = subprocess.check_output(cmd_to_reboot_device, shell=True)
            print(output)
            time.sleep(60) # wait for the device to be back up and reinitialize

        except subprocess.TimeoutExpired:
            print(f'Failed to Reboot the device..')
            raise Exception("Exception in rebooting the device..")

    # once the test-run is done sleep for 5s
    time.sleep(2) # after execution of every option, sleep for 5 secs to reinitialize

    # TODO: check if the number of captures in media folder is equal to count in n

    print("#### End of run #####")

print("========= END of SNAPSHOT-mode run ==========")


# TODO: Process the exection dcitonhary and find out for which all options, supernova test-execution failed in SNAPSHOT mode
'''
print("Printing all the options where supernova_test execution failed.. in SNAPSHOT MODE")
for k, v in exec_time_dict.items():
    if "Exception encountered" in v:
        print(k)

print("Printing successful execution times of all the options.. in SNAPSHOT MODE")
for k, v in exec_time_dict.items():
    if "Exception encountered" not in v:
        print(k, v)
'''

#### Loop through all presets for LIVE_STREAMING mode ####
print("========= Start of LIVESTREAMING-mode run ==========")

exec_time_dict_live={} # dictionary to hold execution times at the end of execution of every option(test scenario)

for option in options:

    print("#### Start of individual run - live-streaming #####")

    print(option)

    start_time = time.time() # Start timer

    # Set the light conditions in the SOL box
    try:
        light.set_light(**option)
    except Exception as e:
        print(e)

        print("Sleep for 2 secs before retrying")
        time.sleep(2) # sleep for 2 secs before retrying it

        # there was exception, hence reTrying to set the light in the box for second time..
        print("There was exception, hence reTrying to set the light in the box for second time..")
        try:
            light.reconnect()
        except Exception as e:
            exec_time_dict[str(option)]="Exception in setting light env in sol box." 
            continue

    print(f"Chromameter readout:{light.get_avg_luminance()}")
    msg=""
    try:
        supernova_test(option, today, chromameter, capture_mode='LIVESTREAMING')    # execute the tests for this given option
    except Exception as e:
        msg="Exception encountered while executing the test, may be timeout exception" 
        
    end_time = time.time() # End timer

    elapsed_time = end_time - start_time # Execution time

    if len(msg)==0:
        exec_time_dict_live[str(option)]=elapsed_time     # make an entry into the exec_time diectionary, execution time taken for executing this option
    else:
        exec_time_dict_live[str(option)]=msg              # if there is an exception during execution, login a message in the dictionary instead of execution time..

    # Rebooting the device on completion of one run of lux values from 0-1000
    if option['luminance'] == 1.0:
        try:
            #import pdb; pdb.set_trace()
            print(f'Rebooting the device at the end of run of lux from 0-1000')
            output = subprocess.check_output(cmd_to_reboot_device, shell=True)
            print(output)
            time.sleep(60) # wait for the device to be back up and reinitialize

        except subprocess.TimeoutExpired:
            print(f'Failed to Reboot the device..')
            raise Exception("Exception in rebooting the device..")

    # once the test-run is done sleep for 5s
    time.sleep(2) # after execution of every option, sleep for 5 secs to reinitialize

    # TODO: check if the number of captures in media folder is equal to count in n

    print("#### End of run #####")

print("========= END of LIVESTREAMING-mode run ==========")


# TODO: Process the exection dcitonhary and find out for which all options, supernova test-execution failed in LIVESTREAMING mode; exec_time_dict_live
'''
print("Printing all the options where supernova_test execution failed.. in SNAPSHOT MODE")
for k, v in exec_time_dict_live.items():
    if "Exception encountered" in v:
        print(k)

print("Printing successful execution times of all the options.. in SNAPSHOT MODE")
for k, v in exec_time_dict.items():
    if "Exception encountered" not in v:
        print(k, v)
'''

print("Done with Test")




from enum import Enum
import RPi.GPIO as GPIO
from TCS34725 import TCS34725
import subprocess
import numpy as np
import time

class Pattern(Enum):
    '''
    Enum class to denote 0 for None; 1 for SOLID; 2 for BLINK 
    '''
    NONE  = 0
    SOLID = 1
    BLINK = 2

class ColorSensor:
    def __init__(self):
        self.color = None
        self.pattern = None
        self.start_capture = False
        self.sensor = TCS34725(0X29, debug=False)
        self.sensor.SetLight(0)
        self.raw_colors = []
        self.colors_rgb_unique_samples_list=[]
        self.timestampsdict={}
        
        # Constant RGB color patterns from CSS table..
        self.css_colors = [[0,0,0],[255,255,255],[255,0,0],[0,255,0],[0,0,255],[255,255,0],[0,255,255],[250,0,255],[192,192,192],[128,128,128],[128,0,0],[0,128,0],[128,0,128],[0,128,128],[0,0,128]]
        
    def sensor_init(self):
        '''
        Initialize color sensor
        '''
        
        try:
            if self.sensor.TCS34725_init() == 1:
                print("TCS34725 initialization error!!")
                return False
            else:
                print("TCS34725 initialization success!!")
                self.sensor.SetLight(0)
                time.sleep(0.5)
                return True
        except Exception as e:
            print("Error in sensor init", e)
            GPIO.cleanup()
            return False
            
    def start_detection_collect_rgb_samples(self, num_samples=30):
        '''
        Start detection and collect RGB samples into self.raw_colors list
        '''
        
        for i in range(num_samples):
            self.sensor.Get_RGBData()
            self.sensor.GetRGB888()
            color = [self.sensor.RGB888_R, self.sensor.RGB888_G, self.sensor.RGB888_B]
            self.raw_colors.append(color)
            
            tstamp = time.time()
            self.timestampsdict[tstamp]=color
            
            time.sleep(0.2)
            
    def remove_consecutive_duplicate_patterns(self, elements):
        '''
        Each RGB sample will be a list like this [200,0,0]; over 10 secs, we collect n number
        of samples like lets say 20 samples; this function will remove all the duplicate patterns
        and return back single unique RGB sample pattern..
        '''
        
        s = [''.join(map(lambda x:str(x), e)) for e in elements]
        t = list(set(s))
        
        unique_rbg_list=[]
        for e in t:
            l = [int(e[i:i+3]) for i in range(0, len(e), 3)]
            unique_rbg_list.append(l)
        return unique_rbg_list
        
    def get_detected_color_pattern(self):
        '''
        There are 3 color patterns: NONE, SOLILD, BLINK
        collect the samples (RGB patterns), remove all the duplicate patterns,
        check for number of RGB colors-patterns in the list; if there is one then it is SOLID;
        if it is more than 1, then it is BLINK
        '''
       
        self.colors_rgb_unique_samples_list = self.remove_consecutive_duplicate_patterns(self.raw_colors)

        num_colors = len(self.colors_rgb_unique_samples_list)
        print(f"Total colors Found {num_colors}", self.raw_colors)
        if num_colors == 0:
            self.pattern = Pattern.NONE
        elif num_colors == 1:
            self.pattern = Pattern.SOLID
        else:
            self.pattern = Pattern.BLINK
            
        return str(self.pattern.name) + ":" + str(self.colors_rgb_unique_samples_list)        
            
    def closest_rgb_color_in_css(self, color):
        '''
        Given RGB co-ordinates, compute the distance to each of the RGB co-ordinates in CSS color
        color table.. and find the the closest match to 'A' specific color in CSS table..
        '''
    
        colors = np.array(self.css_colors)
        color = np.array(color)
        distances = np.sqrt(np.sum((colors-color)**2,axis=1))
        index_of_smallest = np.where(distances==np.amin(distances))
        smallest_distance = colors[index_of_smallest]
        return smallest_distance.tolist()

    def get_rgb_colornames(self, rgb_list):
        '''
        For each RBG sample pattern, get the closest color in CSS table and return the list of colors.
        '''
       
        res_list=[]
        for rgb in rgb_list:

            closest_rgb = self.closest_rgb_color_in_css(rgb)[0] # get the RBG value closest to the one in CSS table
            print("RGB color closest to {} is : {}".format(rgb, closest_rgb))
            
            if not isinstance(closest_rgb, list) or len(closest_rgb)!=3:
                raise Exception("Invalid RGB list passed, length is wrong or its not a list")
       
            if not all(0<=value<=255 for value in closest_rgb):
                raise Exception("Value does not fall between 0-255")
       
            try:
                import webcolors
                result_color = webcolors.rgb_to_name(closest_rgb)
                res_list.append(result_color)
            except ValueError as e:
                print("Invalid Color: ")
                print(e)
                res_list.append(None)
               
        return res_list
    
    def get_blinking_time_period(self,blink_color_pattern=None, colors=None):
        '''
        Lets there is a blink, RG-blink-RG
        this function ascertains the blinking time-period between firstR and SecondG
        '''
        print(self.timestampsdict)
        
        for k, v in self.timestampdict.items():
            if v==self.colors_rgb_unique_samples_list[0]:
                stimestamp=k
                break
    
        cnt2=0
        for k, v in self.timestampdict.items():
            if v==self.colors_rgb_unique_samples_list[1]:
                 cnt2+=1
                 if cnt2==2:
                     endtimestamp=k
                     break
        return Math.abs(stimestamp-endtimestamp)

    @staticmethod
    def import_with_auto_install(package):
        '''
        Install webcolors package if it is not already installed
        '''
                
        try:
            import webcolors
            print("webcolors package imported successfully!!")
        except ImportError:
            import sys
            subprocess.check_call([sys.executable, "-m", "pip", "install", 'webcolors'])
            import webcolors

    def cleanup(self):
        GPIO.cleanup()

if __name__ == "__main__":
    '''
    Steps:
       1) Initialize color sensor.
       2) Start detection and collect RGB samples.
       3) Get Detected color pattern, None or Solid or Blink.
       4) Get unique color patterns from the collected RBG samples list.
       5) For each of the RGB color pattern, find the closest RGB color pattern in the CSS table.
       6) Find the resultant colornames for each of the unique color RGB pattern.
       7) Invoke cleanup and release the resources.
    '''
    
    # Create ColorSensor package
    sensor = ColorSensor()
   
    # Check and install webcolors package to return colorname corresponding to rgb tuple
    sensor.import_with_auto_install("webcolors")
   
    print("Create ColorSensor object and initiatlize color sensor..")
    sensor.sensor_init()
   
    print("Capturing Color data.. for 10 secs")
    sensor.start_detection_collect_rgb_samples()
    
    # sleep for 5 secs after detection before computing the color pattern and colornames
    time.sleep(5)
    
    if len(sensor.colors_rgb_unique_samples_list)==2:
        blinking_time_period = sensor.get_blinking_time_period()
   
    print("Get detected color pattern.")
    result = sensor.get_detected_color_pattern() # capture color pattern
    print("Results:" , result)
   
    print("Convert the results to actual color_names.")
    color_names = sensor.get_rgb_colornames(sensor.colors_rgb_unique_samples_list)
    print("Resultant ColorNames: " + str(color_names))
from bokeh.plotting import figure, show, output_file
from bokeh.models import LinearColorMapper, SingleIntervalTicker, ColorBar, Title, Range1d, ColumnDataSource
import random
from bokeh.io import export_png
import numpy as np 
import warnings
import configparser
# import matplotlib.pyplot as plt
from argparse import ArgumentParser
from datetime import datetime,timedelta
from scipy.special import binom
from scipy.special import gammaincinv
warnings.simplefilter("error", RuntimeWarning)

# Parse command line input
parser = ArgumentParser()
parser.add_argument('obsfile', help='supply a list of observations')
args = parser.parse_args()

observations = np.loadtxt(args.obsfile,dtype={'names': ('dateobs', 'duration', 'field'), 'formats': ('U32','f8','U32')})
uniquefields = np.unique(observations['field'])
# print(uniquefields)
# exit()
if observations.size>1:
    observations = observations[np.argsort([datetime.fromisoformat(o) for o in observations['dateobs']])]
    
# Read rate.ini settings into variables

params = configparser.ConfigParser()
params.read('rate.ini')
conf_lev = np.float(params['STATISTICAL']['confidence'])
extract_rad = np.float(params['DATA']['extract_rad'])
sigtonoise = np.float(params['STATISTICAL']['sigtonoise'])
tsnap = np.float(params['DATA']['minint'])/60./60./24.
num_skyrgns = len(uniquefields)
detections = int(params['DATA']['detections'])

if detections > 0:
    alpha = 1-conf_lev
    upperlimitpoisson = gammaincinv(detections+1, 1-alpha/2)
    lowerlimitpoisson = gammaincinv(detections,alpha/2.)

if observations.size>1:
    start_survey = min([datetime.fromisoformat(o) for o in observations['dateobs']])
    stop_survey = max([datetime.fromisoformat(o) for o in observations['dateobs']])
    stop_survey_ind = np.argmax([datetime.fromisoformat(o) for o in observations['dateobs']])
    tsurvey = ((stop_survey + timedelta(seconds=observations[stop_survey_ind][1])) - start_survey).total_seconds()/60/60/24
elif observations.size==1:
    start_survey = datetime.fromisoformat(str(observations['dateobs'])) 
    stop_survey = datetime.fromisoformat(str(observations['dateobs']))
    tsurvey = timedelta(seconds=np.float(observations['duration'])).total_seconds()/60/60/24
else:
    print("must have at least one observation")
    exit()
onsourcetime = np.sum(observations['duration'])/60/60/24
sampletimescales = np.geomspace(tsnap, tsurvey, num=10)


if observations.size > 1:
    tgap = np.zeros((len(observations)-1,))
    tgap = np.array([(datetime.fromisoformat(observations[i+1][0]) - (datetime.fromisoformat(observations[i][0]) + timedelta(seconds=observations[i][1]))).total_seconds()/60/60/24 for i in range(len(observations)-1)])
elif observations.size == 1:
    tgap = 1e-12 # some small number


def npairsperT(T):
    timescalearr = []
    npairarr = []
    imhist = np.zeros(len(T),dtype='i4')
    for i in range(len(T)):
        t = T[i]
        startbin = datetime.fromisoformat(observations['dateobs'][0])
        stopbin = datetime.fromisoformat(observations['dateobs'][-1]) + timedelta(days=observations['duration'][-1]) + timedelta(days=t)
        totalbins = int(round((stopbin-startbin).total_seconds()/timedelta(days=t).total_seconds()))

        if t<min(observations['duration']):
            imhist[i] = int(round(onsourcetime/t))
        else:
            for j in range(totalbins):
                localbinL = (startbin + j*timedelta(days=t))
                localbinR = (startbin + (j+1)*timedelta(days=t))
                obsdates = [datetime.fromisoformat(d) for d in observations['dateobs']]
                obsdurs = [timedelta(days=d) for d in observations['duration']]          
                for (date, dur) in zip(observations['dateobs'], observations['duration']):
                    startobs = datetime.fromisoformat(date)
                    endobs = datetime.fromisoformat(date) + timedelta(days=dur)
                    leftcond = localbinL<=endobs
                    observedinbin = max(0,(min(localbinR,endobs) - max(localbinL, startobs)).total_seconds())/60/60/24
                    if (max(localbinL, startobs) < min(localbinR,endobs)) and observedinbin>tsnap:
                        imhist[i]+=1
                        break
    imhist-=1
    return imhist
    

def prob_gaps(tdur): # eqn 3.12 in Dario's thesis
    prob = np.zeros(tdur.shape,dtype=float)
    for i in range(len(tdur)):
        tau = tdur[i]
        numerator = tgap-tau
        if numerator.size>1:
            numerator[numerator<0]=0
        else:
            numerator = 0
        prob[i] =  np.sum(numerator)/tsurvey
    return prob

def transrate(T): # eqn 3.15 in Dario's thesis

    omega = np.pi*extract_rad**2
    #The constant converts to 1/sky
    if detections==0:
        return -41252.96*np.log(1-conf_lev)/num_skyrgns/omega/(tsurvey+T)/(1-prob_gaps(T))
    else:
        return 4152.96*lowerlimitpoisson/num_skyrgns/omega/(tsurvey+T)/(1-prob_gaps(T)), 4152.96*upperlimitpoisson/num_skyrgns/omega/(tsurvey+T)/(1-prob_gaps(T))
    
    
def transrateuncorr(T): # eqn 3.15 in Dario's thesis

    omega = np.pi*extract_rad**2
    #The constant converts to 1/sky
    if detections==0:
        return -41252.96*np.log(1-conf_lev)/num_skyrgns/omega/npairsperT(T)/sampletimescales[npairsperT(sampletimescales)>1]
    else:
        return 4152.96*lowerlimitpoisson/omega/num_skyrgns/npairsperT(T)/sampletimescales[npairsperT(sampletimescales)>1], 4152.96*upperlimitpoisson/omega/num_skyrgns/npairsperT(T)/sampletimescales[npairsperT(sampletimescales)>1]
    
tdur = sampletimescales
if detections == 0:
    rateplot = figure(title=" ", x_axis_type = "log", y_axis_type = "log" )
    rateplot.cross(x=tdur, y=transrate(tdur), size=15, color="#386CB0", legend_label="Gap Corrected")
    rateplot.diamond(x=tdur[npairsperT(tdur)>1], y=transrateuncorr(tdur[npairsperT(tdur)>1]), size=15, color="#b07c38", legend_label="Uncorrected")
    rateplot.add_layout(Title(text="Duration (days)", align="center"), "below")
    rateplot.add_layout(Title(text="Transient Rate (per sky, per day)", align="center"), "left")
    rateplot.toolbar.logo = None
    rateplot.toolbar_location = None
    rateplot.toolbar.active_drag = None
    rateplot.toolbar.active_scroll = None
    rateplot.toolbar.active_tap = None
    output_file("rateplot.html", title = "Transient Rate")
    #export_png(p, filename=file + "_ProbContour.png")
    show(rateplot)
else:
# 
    rateplot = figure(title=" " , x_axis_type = "log", y_axis_type = "log")
    uncorrlower, uncorrupper = transrateuncorr(tdur[npairsperT(tdur)>1])
    corrlower, corrupper = transrate(tdur)
    rateplot.vbar(x=tdur+5e-2*tdur, width=5e-2*tdur,bottom=uncorrlower, top=uncorrupper, color="#b07c38", legend_label="Uncorrected")
    rateplot.vbar(x=tdur[npairsperT(tdur)>1]-5e-2*tdur[npairsperT(tdur)>1], width=5e-2*tdur[npairsperT(tdur)>1],bottom=corrlower, top=corrupper, color="#386CB0", legend_label="Corrected")
    rateplot.y_range = Range1d(np.min(np.concatenate((uncorrlower,corrlower)))*0.9,np.max(np.concatenate((corrupper,uncorrupper)))*1.1)
    rateplot.x_range = Range1d(np.min(tdur)*0.9,np.max(tdur)*1.1)
    rateplot.add_layout(Title(text="Duration (days)", align="center"), "below")
    rateplot.add_layout(Title(text="Transient Rate (per sky, per day)", align="center"), "left")
    rateplot.toolbar.logo = None
    rateplot.toolbar_location = None
    rateplot.toolbar.active_drag = None
    rateplot.toolbar.active_scroll = None
    rateplot.toolbar.active_tap = None
    output_file("rateplot.html", title = "Transient Rate")
    show(rateplot)





    

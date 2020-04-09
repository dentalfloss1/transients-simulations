import configparser
import random
import time
import datetime
import numpy as np
import os
import argparse
import math
from bokeh.plotting import figure, show, output_file
from bokeh.models import LinearColorMapper, SingleIntervalTicker, ColorBar, Title
import scipy.interpolate as interpolate
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.cm as cm
from matplotlib import rc
import pylab
from scipy.stats import norm
from scipy.special import erf
rc('text', usetex=False)


def get_configuration():
    """Returns a populated configuration"""
    argparser = argparse.ArgumentParser()
    argparser.add_argument("--observations", help="Observation filename")    # format date YYYY-MM-DDTHH:MM:SS.mmmmmm, dur (day), sens (Jy)
    argparser.add_argument("--dump_intermediate", action='store_true', help="Dump data from intermediate steps")
    argparser.add_argument("--keep", action='store_true', help="Keep previous bursts")
    argparser.add_argument("--stat_plot", action='store_true', help="Performs statistics and plots results")
    argparser.add_argument("--just_plot", action='store_true', help="Just plots results")
    argparser.add_argument("--just_stat", action='store_true', help="Just plots results")


    return argparser.parse_args()

def read_ini_file(filename = 'config.ini'):
    params = configparser.ConfigParser()
    params.read(filename)

    return params

def write_source(filename, bursts):
    with open(filename, 'a') as f:
        for burst in bursts:
            f.write("{}\t{}\t{}\n".format(burst[0], burst[1], burst[2]))            
        f.flush()

def initialise():
    
# Transients parameters
    params = read_ini_file()
    n_sources = np.long(float(params['INITIAL PARAMETERS']['n_sources']))  
    fl_min = np.float(params['INITIAL PARAMETERS']['fl_min'])     
    fl_max = np.float(params['INITIAL PARAMETERS']['fl_max'])   
    flux_err = np.float(params['INITIAL PARAMETERS']['flux_err'])
    dmin = np.float(params['INITIAL PARAMETERS']['dmin'])      
    dmax = np.float(params['INITIAL PARAMETERS']['dmax'])    
    det_threshold = np.float(params['INITIAL PARAMETERS']['det_threshold']) 
    extra_threshold = np.float(params['INITIAL PARAMETERS']['extra_threshold']) 
    file = params['INITIAL PARAMETERS']['file']   
    lightcurvetype = params['INITIAL PARAMETERS']['lightcurvetype']  
# Observational Parameters, if simulated

    nobs = int(params['SIM']['nobs'])
    obssens = np.float(params['SIM']['obssens'])
    obssig = np.float(params['SIM']['obssig'])
    obsinterval = int(params['SIM']['obsinterval'])
    obsdurations = np.float(params['SIM']['obsdurations'])

    config = get_configuration() # parses arguments, see above
    if lightcurvetype != 'tophat' and lightcurvetype != 'fred' and lightcurvetype != 'gaussian':
        print('Type of transient not recognised.\nUse tophat, fred, or gaussian.')
        exit()
    file = file + '_' + lightcurvetype

    obs = observing_strategy(config.observations, det_threshold, nobs, obssens, obssig, obsinterval, obsdurations)

    if config.just_plot: 
        plots(obs, file, extra_threshold, det_threshold, flux_err, lightcurvetype)
        print('done')
        exit()        

    if not config.keep: # if you to save the burst we save it:
        with open(file + '_SimTrans', 'w') as f:
            f.write('# Tstart\tDuration\tFlux\n')        ## INITIALISE LIST OF SIMILATED TRANSIENTS
    
        with open(file + '_DetTrans', 'w') as f:
            f.write('# Tstart\tDuration\tFlux\n')        ## INITIALISE LIST OF DETECTED TRANSIENTS
    

    start_time = obs[0][0] #recall that obs has the form: start, duration, sensitivity. Therefore this is the start of the very first observation.
    end_time = obs[-1][0] + obs[-1][1] #The time that the last observation started + its duration. end_time-start_time = duration of survey
    simulated = generate_sources(n_sources, file, start_time, end_time, fl_min, fl_max, dmin, dmax, config.dump_intermediate, lightcurvetype) # two functions down
    det = detect_bursts(obs, file, flux_err, det_threshold, extra_threshold, simulated, lightcurvetype, config.dump_intermediate)
    
    if config.stat_plot:
        with open(file + '_Stat', 'w') as f:
            f.write('# Duration\tFlux\tProbability\n')        ## INITIALISE LIST OF STATISTICS
        statistics(file, fl_min, fl_max, dmin, dmax, det, simulated)
        plots(obs, file, extra_threshold, det_threshold, flux_err, lightcurvetype)
    if config.just_stat:
        with open(file + '_Stat', 'w') as f:
            f.write('# Duration\tFlux\tProbability\n')        ## INITIALISE LIST OF STATISTICS
        statistics(file, fl_min, fl_max, dmin, dmax, det, simulated)

def observing_strategy(obs_setup, det_threshold, nobs, obssens, obssig, obsinterval, obsdurations):
    observations = []
    try:
        with open(obs_setup, 'r') as f:
            for line in f:
                if len(line) == 0 or line[0] == '#':
                    continue
                cols = line.split('\t')
                tstart = time.mktime(datetime.datetime.strptime(cols[0], "%Y-%m-%dT%H:%M:%S.%f").timetuple())/(3600*24)    #in days
                tdur = float(cols[1])    # in days
                sens = float(cols[2]) * det_threshold    # in Jy
                observations.append([tstart, tdur, sens])
    except TypeError:
        for i in range(nobs):
            tstart = (time.mktime(datetime.datetime.strptime("2019-08-08T12:50:05.0", "%Y-%m-%dT%H:%M:%S.%f").timetuple()) + 60*60*24*obsinterval*i)/(3600*24)    #in days at an interval of 7 days
            tdur = obsdurations
            sens = random.gauss(obssens, obssig) * det_threshold # in Jy. Choice of Gaussian and its characteristics were arbitrary.
            observations.append([tstart,tdur,sens])
            
    observations = np.array(observations,dtype=np.float64)
    obs = observations[observations[:,0].argsort()] # sorts observations by day

    return obs

def generate_sources(n_sources, file, start_time, end_time, fl_min, fl_max, dmin, dmax, dump_intermediate, lightcurve):
    bursts = np.zeros((n_sources, 3), dtype=np.float64)
    #The following two functions pick a random number that is evenly spaced logarithmically
    bursts[:,1] = np.absolute(np.power(10, np.random.uniform(np.log10(dmin), np.log10(dmax), n_sources))) # random number for duration
    bursts[:,2] = np.absolute(np.power(10, np.random.uniform(np.log10(fl_min), np.log10(fl_max), n_sources))) # random number for flux
    if(lightcurve == "gaussian"):  
        bursts[:,0] = np.random.uniform(start_time - bursts[:,1], end_time + bursts[:,1], n_sources)
    elif((lightcurve == "tophat") or (lightcurve == "fred")):
        bursts[:,0] = np.random.uniform(start_time - bursts[:,1], end_time, n_sources) # randomize the start times based partly on the durations above
    
    bursts = bursts[bursts[:,0].argsort()] # Order on start times
    if dump_intermediate: 
        write_source(file + '_SimTrans', bursts) #file with starttime\tduration\tflux
        print("Written Simulated Sources")
    return bursts

def detect_bursts(obs, file, flux_err, det_threshold, extra_threshold, sources, lightcurve, dump_intermediate):
    single_detection = np.array([],dtype=np.uint32)
    extra_detection = np.array([],dtype=np.uint32)

    for o in obs:
        start_obs, duration, sensitivity = o
        extra_sensitivity = sensitivity * (det_threshold + extra_threshold) / det_threshold
        end_obs = start_obs + duration
        
        # The following handles edge cases
        if lightcurve == 'fred':
            ## Transients start before observation ends
            single_candidate = np.where(sources[:,0] < end_obs)[0]
        elif lightcurve == 'tophat':
            ## Transients end after observation starts and start before observation ends
            single_candidate = np.where((sources[:,0] + sources[:,1] > start_obs) & (sources[:,0] < end_obs))[0] # Take all of the locations that qualify as a candidate. The zero index is a wierd python workaround
        elif lightcurve == 'gaussian':
             single_candidate = np.where(sources[:,0] == sources[:,0])[0]
            ## Transients start before observation ends
#            single_candidate = np.where(sources[:,0] < end_obs)[0]

        # filter on integrated flux
        F0_o = sources[single_candidate][:,2]
        # error = np.sqrt((abs(random.gauss(F0_o * flux_err, 0.05 * F0_o * flux_err)))**2 + (sensitivity/det_threshold)**2) 
        F0 = F0_o # random.gauss(F0_o, error) # Simulate some variation in source flux of each source.

        tau = sources[single_candidate][:,1] # Durations
        t_burst = sources[single_candidate][:,0] # start times
        tstart = np.maximum(t_burst, start_obs) - t_burst # How much time passed in which the transient was on, but not being observed in the survey.

        if lightcurve == 'fred':
            tend = end_obs - t_burst # Burst is never really "Off" so, how long is it on? 
            flux_int = np.multiply(F0, np.multiply(tau, np.divide(np.exp(-np.divide(tstart,tau)) - np.exp(-np.divide(tend,tau)), (end_obs-start_obs))))
        
        elif lightcurve == 'tophat':
            tend = np.minimum(t_burst + tau, end_obs) - t_burst
            flux_int = np.multiply(F0, np.divide((tend - tstart), (end_obs-start_obs)))

        elif lightcurve == 'gaussian':
            tend = np.minimum(t_burst + tau, end_obs) - t_burst
            flux_int = np.sqrt(2.0*np.pi)*(tau/(10.0*(end_obs-start_obs)))*np.multiply(F0, norm.cdf(end_obs , loc = t_burst + (tau/2.0), scale = tau/10.0)-norm.cdf(start_obs , loc = t_burst + (tau/2.0), scale = tau/10.0))
            # flux_int = np.multiply(F0,(-1.0/2.0)*erf((3.0*(-2.0*end_obs+2.0*t_burst+tau))/(np.sqrt(2)*tau))+(1.0/2.0)*erf((3.0*(-2.0*start_obs+2.0*t_burst+tau))/(np.sqrt(2)*tau)))
        candidates = single_candidate[(flux_int > sensitivity)]
        extra_candidates = np.array(single_candidate[flux_int > extra_sensitivity])

        single_detection = np.append(single_detection, candidates)
        extra_detection = np.append(extra_detection, extra_candidates)
        
    dets = unique_count(single_detection)
    detections = dets[0][np.where(dets[1] < len(obs))[0]]
    detections = detections[(np.in1d(detections, extra_detection))] # in1d is deprecated consider upgrading to isin
    if dump_intermediate:
        write_source(file + '_DetTrans', sources[detections])
        print("Written Detected Sources")
    return sources[detections]

def unique_count(a):
    unique, inverse = np.unique(a, return_inverse=True)
    count = np.zeros(len(unique), np.int)
    np.add.at(count, inverse, 1)
    return [unique, count]


def statistics(file, fl_min, fl_max, dmin, dmax, det, all_simulated):

    flux_ints = np.geomspace(fl_min, fl_max, num=int(round((np.log10(fl_max)-np.log10(fl_min))/0.05)), endpoint=True)
    dur_ints = np.geomspace(dmin, dmax, num=int(round((np.log10(dmax)-np.log10(dmin))/0.05)), endpoint=True)

    fluxes = np.array([],dtype=np.float32)
    durations = np.array([],dtype=np.float32)
#    probabilities = np.array([],dtype=np.float32)

#    stats = np.zeros(((len(flux_ints)-1)*(len(dur_ints)-1), 3), dtype=np.float32)
    stats = np.zeros(((len(flux_ints)-1)*(len(dur_ints)-1), 5), dtype=np.float32)
    
    alls = np.array([],dtype=np.uint32)
    dets = np.array([],dtype=np.uint32)
    
    doit_f = True
    for i in range(len(dur_ints) - 1):

        all_dur = np.array([],dtype=np.uint32)
        det_dur = np.array([],dtype=np.uint32)

        all_dur = np.append(all_dur, np.where((all_simulated[:,1] >= dur_ints[i]) & (all_simulated[:,1] < dur_ints[i+1]))[0])
        det_dur = np.append(det_dur, np.where((det[:,1] >= dur_ints[i]) & (det[:,1] < dur_ints[i+1]))[0])
        durations = np.append(durations, dur_ints[i] + dur_ints[i+1]/2.)

        for m in range(len(flux_ints) - 1):
            dets = np.append(dets, float(len(np.where((det[det_dur,2] >= flux_ints[m]) & (det[det_dur,2]< flux_ints[m+1]))[0])))
            alls = np.append(alls, float(len(np.where((all_simulated[all_dur,2] >= flux_ints[m]) & (all_simulated[all_dur,2] < flux_ints[m+1]))[0])))

            if doit_f == True:
                fluxes = np.append(fluxes,  (flux_ints[m] + flux_ints[m+1])/2.)

        doit_f = False

    probabilities = np.zeros(len(alls),dtype=np.float32)
    toprint_alls = alls[np.where((alls[:] != 0.))]
    toprint_dets = dets[np.where((alls[:] != 0.))]

    probabilities[np.where((alls[:] != 0.))] = dets[np.where((alls[:] != 0.))] / alls[np.where((alls[:] != 0.))]
    
    stats[:,0] = np.repeat(durations, len(fluxes))
    stats[:,1] = np.tile(fluxes, len(durations))
    stats[:,2] = probabilities
    stats[:,3] = dets
    stats[:,4] = alls



#    write_source(file + '_Stat', stats)
    write_stat(file + '_Stat', stats)

    print("Written Statistics")

    return stats

def write_stat(filename, bursts):
    with open(filename, 'a') as f:
        for burst in bursts:
#            f.write("{0}\t{1}\t{2}\t{3}\t{4}\n".format(burst[0], burst[1], burst[2], burst[3], burst[4]))        # for python 2.6 (krieger)
            f.write("{}\t{}\t{}\t{}\t{}\n".format(burst[0], burst[1], burst[2], burst[3], burst[4]))        # for python 2.7 (struis)
        f.flush()


def plots(obs, file, extra_threshold, det_threshold, flux_err, lightcurve):
    toplot = np.loadtxt(file + '_Stat')

    # toplot[:,0] = np.log10(toplot[:,0])
    # toplot[:,1] = np.log10(toplot[:,1])

    gaps = np.array([],dtype=np.float32)
    for i in range(len(obs)-1):
        gaps = np.append(gaps, obs[i+1,0] - obs[i,0] + obs[i,1])
        # gaps = np.append(gaps, obs[i+1,0] - obs[i,0])
    min_sens = min(obs[:,2])
    max_sens = max(obs[:,2])
    extra_thresh = max_sens / det_threshold * (extra_threshold + det_threshold)
    sens_last = obs[-1,2]
    sens_maxgap = obs[np.where((gaps[:] == max(gaps)))[0]+1 ,2][0]

    durmax = obs[-1,0] + obs[-1,1] - obs[0,0]
    day1_obs = obs[0,1]
    max_distance = max(gaps)

    dmin=min(toplot[:,0])
    dmax=max(toplot[:,0])
    flmin=min(toplot[:,1])
    flmax=max(toplot[:,1])

    xs = np.geomspace(dmin, dmax, num = 7000)
    ys = np.geomspace(flmin, flmax, num = 7000)
    if (lightcurve == 'fred'):    
        durmax_y_max_val_ind = np.where((np.exp(-(durmax - day1_obs + xs) /  xs) - np.exp(-((durmax + xs) / xs))) < 1e-50 )
        durmax_y_good_val_ind =  np.where((np.exp(-(durmax - day1_obs + xs) /  xs) - np.exp(-((durmax + xs) / xs))) > 1e-50 )
        maxdist_y_max_val_ind = np.where((np.exp(-(max_distance / xs)) - np.exp(-(max_distance + day1_obs) / xs)) < 1e-50)
        maxdist_y_good_val_ind =  np.where((np.exp(-(max_distance / xs)) - np.exp(-(max_distance + day1_obs) / xs)) > 1e-50)

        durmax_y = np.zeros(xs.shape,dtype = np.float64)
        maxdist_y = np.zeros(xs.shape, dtype = np.float64)

        durmax_y[durmax_y_good_val_ind[0]] = ((1. + flux_err) * sens_last * day1_obs / xs[durmax_y_good_val_ind[0]]) / (np.exp((-(durmax - day1_obs + xs[durmax_y_good_val_ind[0]])) /  xs[durmax_y_good_val_ind[0]]) - np.exp(-((durmax + xs[durmax_y_good_val_ind[0]])) / xs[durmax_y_good_val_ind[0]]))
        durmax_y[durmax_y_max_val_ind[0]] = np.inf
        maxdist_y[maxdist_y_good_val_ind[0]] =  (((1. + flux_err) * sens_maxgap * day1_obs) /  xs[maxdist_y_good_val_ind[0]])   / (np.exp(-(max_distance / xs[maxdist_y_good_val_ind[0]])) - np.exp(-(max_distance + day1_obs) / xs[maxdist_y_good_val_ind[0]]))
        maxdist_y[maxdist_y_max_val_ind[0]] = np.inf
             
    elif (lightcurve == 'tophat'):
        durmax_x = np.empty(len(ys))
        durmax_x.fill(durmax)
        maxdist_x = np.empty(len(ys))
        maxdist_x.fill(max_distance)
    
    elif (lightcurve == 'gaussian'):
        durmax_y_max_val_ind = np.where((gausscdf(xs,durmax + xs) - gausscdf(xs, durmax - day1_obs + xs)) <1e-50)
        durmax_y_good_val_ind = np.where((gausscdf(xs,durmax + xs) - gausscdf(xs, durmax - day1_obs + xs)) >1e-50)
        maxdist_y_max_val_ind = np.where((gausscdf(xs,max_distance + day1_obs ) - gausscdf(xs, max_distance))<1e-50)
        maxdist_y_good_val_ind = np.where((gausscdf(xs,max_distance + day1_obs ) - gausscdf(xs, max_distance))>1e-50)

        durmax_y = np.zeros(xs.shape,dtype = np.float64)
        maxdist_y = np.zeros(xs.shape, dtype = np.float64)
        
        durmax_y[durmax_y_good_val_ind[0]] =  ((1. + flux_err) * sens_last * day1_obs  ) / (gausscdf(xs[durmax_y_good_val_ind[0]],durmax + xs[durmax_y_good_val_ind[0]]) - gausscdf(xs[durmax_y_good_val_ind[0]], durmax - day1_obs + xs[durmax_y_good_val_ind[0]])) 
        # durmax_y[durmax_y_good_val_ind[0]] = ((1. + flux_err) * sens_last  ) / (np.sqrt(np.pi/2.0)*(erf((3.0*(-2.0*(durmax - day1_obs + xs[durmax_y_good_val_ind[0])) + xs[durmax_y_good_val_ind[0])))/(xs[durmax_y_good_val_ind[0])*np.sqrt(2.0))) - erf((3.0*(-2.0*(durmax + xs[durmax_y_good_val_ind[0])) + xs[durmax_y_good_val_ind[0]))/(xs[durmax_y_good_val_ind[0])*np.sqrt(2.0))))))
        durmax_y[durmax_y_max_val_ind[0]] = np.inf
        maxdist_y[maxdist_y_good_val_ind[0]] =  ((1. + flux_err) * sens_last * day1_obs ) / (gausscdf(xs[maxdist_y_good_val_ind[0]],max_distance + day1_obs ) - gausscdf(xs[maxdist_y_good_val_ind[0]], max_distance))         
        # maxdist_y[maxdist_y_good_val_ind[0]] =  ((1. + flux_err) * sens_maxgap ) / (np.sqrt(np.pi/2.0)*(erf((3.0*(-2.0*(max_distance) + xs[maxdist_y_good_val_ind[0])))/(xs[maxdist_y_good_val_ind[0])*np.sqrt(2.0))) - erf((3.0*(-2.0*(max_distance + day1_obs ) + xs[maxdist_y_good_val_ind[0]))/(xs[maxdist_y_good_val_ind[0])*np.sqrt(2.0))))))
        maxdist_y[maxdist_y_max_val_ind[0]] = np.inf
            
    day1_obs_x = np.empty(len(ys))
    day1_obs_x.fill(day1_obs)
    
    sensmin_y = np.empty(len(xs))
    sensmin_y.fill(min_sens)
    
    sensmax_y = np.empty(len(xs))
    sensmax_y.fill(max_sens)

    extra_y = np.empty(len(xs))
    extra_y.fill(extra_thresh)

    X = np.geomspace(dmin, dmax, num = 1000)
    Y = np.geomspace(flmin, flmax, num = 1000)

    X, Y = np.meshgrid(X, Y)
    
    Z = interpolate.griddata(toplot[:,0:2], toplot[:,2], (X, Y), method='linear')
    p = figure(title="Three Term Probability Contour Plot",tooltips = [("X", "$X"), ("Y", "$Y"), ("value", "@image")], x_axis_type = "log", y_axis_type = "log")
    p.x_range.range_padding = p.y_range.range_padding = 0
    color_mapper = LinearColorMapper(palette="Viridis256",low = 0.0, high = 1.0)
    color_bar = ColorBar(color_mapper=color_mapper, ticker=SingleIntervalTicker(interval = 0.1), label_standoff=12, border_line_color=None, location=(0,0))
    p.image(image=[Z], x=np.amin(xs), y=np.amin(ys), dw=(np.amax(xs)-np.amin(xs)), dh=(np.amax(ys)-np.amin(ys)),palette="Viridis256")
    if False: 
        if lightcurve == 'fred':
            durmax_y_indices = np.where(durmax_y < np.amax(ys))[0]
            maxdist_y_indices = np.where(maxdist_y < np.amax(ys))[0]
            p.line(xs[durmax_y_indices], durmax_y[durmax_y_indices],  line_width=2, line_color = "red")
            p.line(xs[maxdist_y_indices], maxdist_y[maxdist_y_indices], line_width=2, line_color = "red")
        elif lightcurve == 'tophat':
            p.line(durmax_x, ys,   line_width=2, line_color = "red")
            p.line(maxdist_x, ys,  line_width=2, line_color = "red")
        elif lightcurve == 'gaussian':
            durmax_y_indices = np.where(durmax_y < np.amax(ys))[0]
            maxdist_y_indices = np.where(maxdist_y < np.amax(ys))[0]
            p.line(xs[durmax_y_indices], durmax_y[durmax_y_indices],  line_width=2, line_color = "red")
            p.line(xs[maxdist_y_indices], maxdist_y[maxdist_y_indices],  line_width=2, line_color = "red")

         #  p.line(10**xs, durmax_y,  line_width=2, line_color = "red")
        #   p.line(10**xs, maxdist_y,  line_width=2, line_color = "red")

        if (np.amin(day1_obs_x) > np.amin(ys)): p.line(day1_obs_x, ys,  line_width=2, line_color = "red")
        p.line(xs, sensmin_y,  line_width=2, line_color = "red")
        p.line(xs, sensmax_y,  line_width=2, line_color = "red")
        p.line(xs, extra_y,  line_width=2, line_color = "red")
    p.add_layout(color_bar, 'right')
    p.add_layout(Title(text="Duration (days)", align="center"), "below")
    p.add_layout(Title(text="Transient Flux Density (Jy)", align="center"), "left")
    p.toolbar.logo = None
    p.toolbar_location = None
    p.toolbar.active_drag = None
    p.toolbar.active_scroll = None
    p.toolbar.active_tap = None

    output_file(file + "_ProbContour.html", title = "Probability Contour")
    show(p)
    #f = open( 'durmax_y.log', 'w' )
    #for element in durmax_y:
    #    f.write(str(element)+'\n')
    #f.close()
    #f = open( 'maxdist_y.log', 'w' )
    #for element in maxdist_y:
    #    f.write(str(element)+'\n')
    #f.close()
    #f = open( 'xs.log', 'w' )
    #for element in xs:
    #    f.write(str(element)+',')
    #f.close()

def gausscdf(x, t):
    return (x/10.0)*np.sqrt(np.pi/2.0)*norm.cdf(t, loc = x/2.0, scale = x/10.0)

if __name__ == "__main__":
    initialise()
    print('done')
import numpy as np
import os
import sys
from scipy.integrate import quad
from tqdm import tqdm
# from scipy.integrate import trapezoid
from fractions import Fraction
from decimal import Decimal
import datetime
import subprocess
import uuid
from scipy.integrate import quad_vec
from multiprocessing import Pool

class sbpowerlaw:
    """smoothly broken power law lightcurve class"""
    # class variables
    edges=[1,0] # 1 is a definite edge, tophat is the default and has a definite beginning and end. Therefore it is [1,1]
    def __init__(self, alpha1=0.8, alpha2=-2.1, s=10**0.39, nu0=3, nu=3, beta=-0.61  ):
        # from Mooley et al. 2018 https://arxiv.org/abs/1810.12927
        self.alpha1 = alpha1
        self.alpha2 = alpha2
        self.s = s # smoothness 
        self.nu0 = nu0
        self.nu = nu
        self.beta = beta
        self.fractionalcut = 1/((100)*2**(1/s)*(nu/nu0)**(beta))
         
   
    def earliest_crit_time(self, start_survey, tau):       
        return start_survey - tau

    def latest_crit_time(self, end_survey,tau):
        return end_survey

    def tbreakfromdur(self, t1, tau):
        return np.exp((self.alpha1*np.log(t1) - self.alpha2*np.log(t1+tau))/(self.alpha1 - self.alpha2)) - t1
    def fluxint(self, F0, tcrit, tau, end_obs, start_obs):
        """Return the integrated flux"""
       #  def sbpl(t,tb):
       #       return  ((t/tb)**(-self.s*self.alpha1) + (t/tb)**(-self.s*self.alpha2))**(-1/self.s)
       #  def sbpl2(x):
       #       return  ((x)**(-self.s*self.alpha1) + (x)**(-self.s*self.alpha2))**(-1/self.s)
        intflux = np.zeros(F0.shape)
        t1 = np.maximum(start_obs, tcrit - tau)
        unique_filename = str(uuid.uuid4())+'.csv'
       #  result = np.zeros(len(F0),dtype=float)
        error = np.zeros(len(F0), dtype=float)
        s = self.s
        nu = self.nu
        nu0 = self.nu0
        beta = self.beta
        alpha1 = self.alpha1
        alpha2 = self.alpha2
        def integratelc(mytau, mytc, myf0, t2, t1):
            tb = self.tbreakfromdur(mytc, mytau)
            tstart = t1 - mytc
            tend = t2 - mytc
            sbpl = lambda t: (2**(1/s)) * myf0 * (nu/nu0)**(beta) * ( (t/tb)**(-s*alpha1) * (t/tb)**(-s*alpha2))**(-1/s)
            intflux, error = quad_vec(sbpl, tstart, tend)
            return intflux, error
        intflux = np.zeros(len(F0))
        for i,(mytau, mytc, myf0, t2, t1) in enumerate(zip(tau,tcrit,F0,end_obs,start_obs)):
            intflux[i], error[i] = integratelc(mytau, mytc, myf0, t2, t1)
        return intflux
            
    def lines(self, xs, ys, durmax, max_distance, flux_err, obs):
        gaps = np.array([],dtype=np.float32)
        for i in range(len(obs)-1):
            gaps = np.append(gaps, obs['start'][i+1] - obs['start'][i] + obs['duration'][i])
            # gaps = np.append(gaps, obs[i+1,0] - obs[i,0])
        min_sens = min(obs['sens'])
        max_sens = max(obs['sens'])
        sens_last = obs['sens'][-1]
        day1_obs = obs['duration'][0]
        # durmax_x = np.empty(len(ys))
        # durmax_x.fill(np.log10(durmax))
        durmax_y = np.zeros(xs.shape,dtype=np.float64)
        maxdist_y = np.zeros(xs.shape,dtype=np.float64)
        sens_maxgap = obs['sens'][np.where((gaps[:] == max(gaps)))[0]+1][0]
        start_maxgap = obs['start'][np.where((gaps[:] == max(gaps)))[0]+1][0]
        before_maxgap = obs['start'][np.where((gaps[:] == max(gaps)))[0]][0]
        duration_maxgap = obs['duration'][np.where((gaps[:] == max(gaps)))[0]+1][0]
        sens_last = obs['sens'][-1]
        s = self.s
        nu = self.nu
        nu0 = self.nu0
        beta = self.beta
        alpha1 = self.alpha1
        alpha2 = self.alpha2
        for i in range(len(xs)):
            x = np.power(10,xs[i])
            try:
                tb = self.tbreakfromdur(obs['start'][0],x)
                mytc = obs['start'][0]
                t1 = obs['start'][-1] - mytc
                t2 = obs['start'][-1] + obs['duration'][-1] - mytc
                sbpl = lambda t: (2**(1/s)) * 1 * (nu/nu0)**(beta) * ( (t/tb)**(-s*alpha1) * (t/tb)**(-s*alpha2))**(-1/s)
                result, error = quad_vec(sbpl, t1, t2)
                # result, error = sbpl.integrate((self.alpha1, self.alpha2, self.s, self.tbreakfromdur(obs['start'][0],x), obs['start'][-1] + obs['duration'][-1], obs['start'][0], 1, self.nu, self.nu0, self.beta,obs['start'][-1]))
                durmax_y[i] = (1.+flux_err)*sens_last/result
              #   print('durmax_y ',durmax_y[i], 'duration ',x)
            except exception as e:
                print(e)
                durmax_y[i]=np.inf
            try:
                tb = self.tbreakfromdur(before_maxgap,x)
                mytc = before_maxgap
                t2 = start_maxgap + duration_maxgap - mytc
                t1 = start_maxgap - mytc
                sbpl = lambda t: (2**(1/s)) * 1 * (nu/nu0)**(beta) * ( (t/tb)**(-s*alpha1) * (t/tb)**(-s*alpha2))**(-1/s)
                result, error = quad_vec(sbpl, t1, t2)
                maxdist_y[i] = (1.+flux_err)*sens_maxgap/result
            except exception as e:
                print(e)
                maxdist_y[i] = np.inf
        durmax_x = ' '
        maxdist_x = ' '
        # maxdist_x = np.empty(len(ys))
        # maxdist_x.fill(np.log10(max_distance))        
        durmax_y_indices = np.where((durmax_y < np.amax(10**ys)) & (durmax_y > np.amin(10**ys)))[0]
        maxdist_y_indices = np.where((maxdist_y < np.amax(10**ys)) & (maxdist_y > np.amin(10**ys)))[0]
        
        return  durmax_x, maxdist_x, durmax_y, maxdist_y, durmax_y_indices, maxdist_y_indices

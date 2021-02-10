import glob
import datetime
from casatools import msmetadata, ms 
import sys
from astropy.coordinates import SkyCoord
import argparse
parser=argparse.ArgumentParser(
    description='''Crude script that pulls info from supplied ms or multiple ms using unix wildcards. Always check output. Requires casa6 and astropy.''',
    epilog="""Reads in input from sys.argv[1:]""")
observations = sys.argv[1:]
starttime = datetime.datetime.now().strftime('%y%m%d%Hh%Mm%Ss')
for targetobs in observations:
    def get_integrationtime(s):
        print(s)
        msobj = ms()
        msobj.open(targetobs)
        try:
            return msobj.getscansummary()[str(s)]['0']['IntegrationTime']
        except KeyError:
            return get_integrationtime(s+1)

    try:
        integration_time = get_integrationtime(1)
        start_epoch = datetime.datetime(1858, 11, 17, 00, 00, 00, 00)
        msmd = msmetadata()
        msmd.open(msfile=targetobs)

        timelist = []
        for f in msmd.fieldsforintent('TARGET'):
            for s in msmd.scansforfield(f):
                tmptimelist = []
                for t in msmd.timesforscan(s):
                    tmptimelist.append((start_epoch + datetime.timedelta(seconds=t)))
                pointdict = msmd.phasecenter(f)
                pointdir = SkyCoord([pointdict['m0']['value']],[pointdict['m1']['value']], frame=pointdict['refer'].replace('J2000','fk5'), unit=pointdict['m0']['unit'])
                timelist.append([(tmptimelist[0] - datetime.timedelta(seconds=round(integration_time)/2.0)).strftime('%Y-%m-%dT%H:%M:%S.%f+00:00'),
                                 ((tmptimelist[-1] - tmptimelist[0]) + datetime.timedelta(seconds=round(integration_time)/2.0)).total_seconds(), pointdir.ra.degree, pointdir.dec.degree])
        with open('obslist'+starttime+'.txt', 'a+') as f:
            for t in timelist:
                    f.write("{},{},{},{}\n".format(t[0], t[1], t[2][0], t[3][0]))       
            f.flush()
    except RuntimeError:
        print("Issues with "+targetobs+". Skipping this one")

print('wrote to obslist'+starttime+'.txt')
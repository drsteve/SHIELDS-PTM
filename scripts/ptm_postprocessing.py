import os
import numpy as np
import ptm_tools as pt
from scipy import special
from scipy import linalg

class ptm_postprocessor(object):

    __ckm = 2.998e5
    __csq = 8.988e10
    __mc2 = 5.11e2
    __dtor = np.pi/180.0
    __rtod = 180.0/np.pi

    """
    -------
    Purpose
    -------

    The ptm_postprocessor is an object designed to streamline the analysis of ptm data,
    particularly when coupled with the new rungrid capability of the ptm_input module.

    ------
    Inputs
    ------

    filedir     string      optional, specifies directory where data files are found

    -------
    Outputs
    -------

    See documentation for individual routines

    ------
    Author
    ------

    Jesse Woodroffe
    jwoodroffe@lanl.gov

    ----------------
    Revision History
    ----------------

    6/6/2017    Original code

    """

    def __init__(self,filedir=None):

        if filedir!=None:
            self.__filedir=filedir
        else:
            self.__filedir=os.getcwd()

        self.__set_defaults = True



    def set_source_parameters(self,n_dens=1.0,e_char=0.5,kappa=2.5,mass=1.0):
        """
        -------
        Purpose
        -------

        Set the parameters of a single-component kappa distribution

        ------
        Inputs
        ------

        n_dens      float       optional, number density at source region in cm-3
        e_char      float       optional, characteristic energy of distribution in keV
        kappa       float       optional, spectral index of kappa distribution
        mass        float       optional, particle mass in multiples of electron mass

        -------
        Outputs
        -------

        None

        """

        self.__mc2 *= mass
        self.__ec = e_char
        self.__n = n_dens
        self.__kappa = kappa

        self.__set_defaults = False

        return


    def calculate_flux(self,fluxmap):
        """
        -------
        Purpose
        -------

        Calculate differential particle fluxes from a PTM fluxmap

        ------
        Inputs
        ------

        fluxmap     dictionary      Fluxmap dictionary generated by ptm_tools.parse_map_file

        -------
        Outputs
        -------

        j           array(float)    Differential flux

        """

        if self.__set_defaults:
            self.set_source_parameters()

        ef = fluxmap['final_E']
        ei = fluxmap['init_E']

        gamf=1+ef/self.__mc2

        v=self.__ckm*np.sqrt(gamf*gamf-1.0)/gamf

        Wc=self.__ec*(1.0-1.5/self.__kappa)
        f0=self.__n*(self.__mc2/(self.__csq*Wc*2*np.pi*self.__kappa))**1.5*(special.gamma(self.__kappa+1)/special.gamma(self.__kappa-0.5))
        f=f0*(1+ei/(self.__kappa*Wc))**-(self.__kappa+1)

        #j=1e5*self.__csq*v*v/self.__mc2*f
        j=f*1e5*self.__csq*v*v/self.__mc2

        return j



    def calculate_omnidirectional_flux(self, pav,flux):
        """
        -------
        Purpose
        -------

        Calculate the omnidirectional flux from the differential flux

        ------
        Inputs
        ------

        pav         array(float)    Array of pitch angle bins, not necessarily evenly-spaced
        flux        array(float)    Array of fluxes generated by calculate_flux

        -------
        Outputs
        -------

        omni        array(float)    Omnidirectional fluxes

        """

        Q = pav*self.__dtor
        coef = 4.0*np.pi*np.diff(Q)
        favg=0.5*(flux[:,1:]+flux[:,:-1])
        savg=np.sin(0.5*(Q[1:]+Q[:-1]))

        # This reduction approximates the weighted integral over pitch angles
        omni=np.einsum("i,ji",coef*savg,favg)

        return omni



    def process_run(self, runid, verbose=True):
        """
        -------
        Purpose
        -------

        Read in the results of a PTM simulation and calculate the fluxes

        ------
        Inputs
        ------

        runid       integer     identification tag for run to be analyzed (e.g. 1 for data in map_0001.dat)

        -------
        Outputs
        -------

        results     dictionary  fluxes and associated quantities describing the ptm fluxes. Has keys:
                                "fluxmap"   Raw fluxmap from file
                                "energies"  Energies at which fluxes were calculated
                                "angles"    Pitch angles at which fluxes were calculated
                                "flux"      Differential fluxes
                                "omni"      Omnidirectional fluxes
                                "kappa"     Spectral index of kappa distribution
                                "n_dens"    Particle density in source region
                                "e_char"    Characteristic energy of kappa distribution

        """

        fname = self.__filedir+'/map_{:04}.dat'.format(runid)

        results = {}

        if os.path.isfile(fname):

            fluxmap = pt.parse_map_file(fname)
            flux = self.calculate_flux(fluxmap)
            omni = self.calculate_omnidirectional_flux(fluxmap['angles'],flux)

            results['position']=fluxmap['final_x']
            #results['fluxmap']=fluxmap
            #results['initial_E']=fluxmap['init_E'] 
            #results['final_E']=fluxmap['final_E'] 
            #results['energies']=fluxmap['energies'] 
            #results['angles']=fluxmap['angles']
            #results['flux']=flux
            #results['omni']=omni

            results['kappa']=self.__kappa
            results['n_dens']=self.__n
            results['e_char']=self.__ec

        else:

            raise Exception('Error in process_run: '+fname+ ' not found.')

        if verbose:

            print("Energy grid : ", fluxmap['energies'])
            print("PitchAngle grid : ", fluxmap['angles'])
            print("Final Particle Energies [PA] : ",  fluxmap['final_E'])
            print("Diff Flux [E[PA]]: ", flux)
            print("Omni Flux [E]: ", omni)

        return results  



    def seconds_to_hhmmss(self,tsec):
        """
        -------
        Purpose
        -------

        Convert time in seconds [0,86400) to hours/minutes/seconds

        ------
        Inputs
        ------

        tsec        float       Time in seconds [0,86400)

        -------
        Outputs
        -------

        hh          float       Hours since tsec = 0 (even if 0 is not in tsec)
        mm          float       Minutes of the hour [0,60)
        ss          float       Seconds of the minute [0,60)
        """

        hh = tsec//3600
        mm = (tsec-3600*hh)//60
        ss = tsec-3600*hh-60*mm

        return int(hh), int(mm), int(ss)



    #------Here we define RAM-specific routines----->

    def process_ram_boundary(self,griddir=None,write_files=True,outdir=None,date={'year':2000,'month':1,'day':1}):
        """
        Rungrids are a new configuration option provided in the updated version of ptm_input. 
        In addition to the input files, there is a rungrid.txt file that
        describes the characteristics of each input file (time and location).

        When the RAM boundary is simulated using PTM via rungrid configuration, we are able to
        simplify the post-processing workflow using this routine.
        """

        if griddir==None:

            mydir = self.__filedir

        else:

            mydir = griddir

        fname = mydir+'/rungrid.txt'

        if os.path.isfile(fname):

            rungrid = np.loadtxt(fname,skiprows=1)

            # This is backwards tracing, so fluxes will be calculated at the later
            # time, which is given in the third column

            runids = map(int,rungrid[:,0])
            times = np.unique(rungrid[:,2])
            rvals = np.unique(rungrid[:,3])

            if not np.allclose(rvals,rvals[0],1e-3):
                raise Exception('Error in process_ram_boundary: points are not at fixed radial distance.')

            fluxdata= {'rungrid':rungrid}
            fluxdata['runid']=runids
            fluxdata['times']=times
            fluxdata['R']=rvals[0]
            fluxdata['mlt'] = np.sort(np.unique(rungrid[:,4]))

            for runid in runids:
                fluxdata[runid] = self.process_run(runid)

        else:

            raise Exception('Error in process_rungrid: '+fname+' not found')

        if(write_files):
            self.write_ram_fluxes(fluxdata,date=date,outdir=outdir)

        return fluxdata


    def write_ram_fluxes(self,fluxdata,date={'year':2000,'month':1,'day':1},outdir=None):
        """
        Write time- and space-dependent fluxes in a RAM boundary file
        """

        cadence=(fluxdata['times'][1]-fluxdata['times'][0])//60

        year = date['year']
        month = date['month']
        day = date['day']

        fname = '{:4}{:02}{:02}_ptm_geomlt_{:}-min.txt'.format(year,month,day,cadence)

        nenergy=fluxdata[1]['energies'].size

        # Header lines
        header1='# PTM Particle Fluxes for RAM\n'
        header2='# Header Format string: (a24,a6,2x,a72,36a18)\n'
        header3='# DATA   Format string: (a24,f6.1,2x,36(i2),36(f18.4))\n'

        # This parameter has to be in the file but it's not used by RAM
        nsc = np.ones([nenergy],dtype='int')
        nscstring=(nenergy*'{:2}').format(*nsc)

        # Formatting strings
        headFormat='{:>24}{:>6}  {:>72}'
        dataFormat='{:6.1f}  '+nscstring+(nenergy*'{:18.4f}')
        timeFormat='{:4}-{:02}-{:02}T{:02}:{:02}:{:02}.000Z'

        with open(fname,'w') as f:

            f.writelines(header1);
            f.writelines(header2);
            f.writelines(header3);
            f.writelines(headFormat.format('CCSDS','MLT','NSC')+(nenergy*'{:18}'+'\n').format(*fluxdata[1]['energies']))

            i=0
            for time in fluxdata['times']:
                hour,minute,second = self.seconds_to_hhmmss(time)
                for mlt in fluxdata['mlt']:
                    i+=1
                    saflux = fluxdata[i]['omni']/(4.0*np.pi)
                    # Note asterisk in format statement (*np.r_), this is required for correct passing of values
                    dataline = timeFormat.format(year,month,day,hour,minute,second)+dataFormat.format(*np.r_[mlt,saflux])+'\n'
                    f.writelines(dataline)

        return

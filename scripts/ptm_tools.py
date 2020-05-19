"""
This file contains routines used to read in data from the SHIELDS-PTM particle tracing
simulation as well as to calculate quantities based on the particle data.

Jesse Woodroffe, Steven Morley
last revised May 2020
"""

import numpy as np
from scipy import constants
from scipy import special
from scipy import linalg


ckm = constants.speed_of_light/1e3


class newDict(dict):
    def __init__(self, *args, **kwargs):
        self.attrs = dict()
        if 'attrs' in kwargs:
            if hasattr(kwargs['attrs'], '__getitem__'):
                self.attrs = kwargs['attrs']
            del kwargs['attrs']
        super(newDict, self).__init__(*args, **kwargs)


def parse_trajectory_file(fname):
    """
    This routine reads a file of particle trajectory data generated by the ptm simulation. Data from ptm is
    output in formatted ascii, with the time history of a particle trajectory given by a 8-column array with
    an unknown number of rows. The data from each particle is separated by a "#".

    TIME XPOS YPOS ZPOS VPERP VPARA ENERGY PITCHANGLE

    Results from this routine are returned as a dictionary with the trajectory of each particle stored under
    a separate integer key (0-based indexing: first particle is 0, second is 1, etc.)
    """
    with open(fname, 'r') as f:
        flines = f.readlines()
    # Scan for number of particles in trajectory file
    nparts = sum([1 for l in flines if l.strip().startswith('#')])
    # Make dictionary with metadata describing columns
    # TODO: put this in a form that can be used for numpy record arrays?
    dataDict = newDict(attrs={'header': 'TIME XPOS YPOS ZPOS VPERP VPARA ENERGY PITCHANGLE'})
    for idx, line in enumerate(flines):
        line = line.strip()
        if line.startswith('#'):
            # Starts a particle output section, grab particle ID
            if idx != 0:
                dataDict[pnum] = np.array(parr, dtype=np.float)
            pnum = int(line.split()[1])
            parr = []
        else:
            # Get data associated with particle
            parr.append(line.split())
    # put last particle into output dict
    dataDict[pnum] = np.array(parr, dtype=np.float)

    return dataDict


def parse_map_file(fnames):
    """
    This is a convenience routine to read in a "map" file generated by the PTM simulation. Since the particles
    aren't output in a logical or predictable manner, this routine also assembles the energy--pitch-angle grids
    and returns the results in a dictionary. This is all the information that is needed from SHIELDS-PTM to
    assemble flux maps using the energy_to_flux routine.

    If a list of filenames is passed in, all map files will be assembled as if they had come from the same run.
    The user should be careful to only combine files when it makes physical sense to do so.
    As this uses indices of unique energy and pitch angle, only combine runs with unique sets of these values.
    """
    if isinstance(fnames, str):
        fnames = [fnames]

    with open(fnames[0]) as fh:
        header = fh.readline()
        res = np.loadtxt(fh, skiprows=1)
    for fname in fnames[1:]:
        dum = np.loadtxt(fname, skiprows=1)
        res = np.vstack((res, dum))

    pavec = np.sort(np.unique(res[:, 5]))
    envec = np.sort(np.unique(res[:, 4]))

    sourcepos = header.strip().split()[-3:]
    fluxmap = newDict(attrs={'position': np.array(sourcepos, dtype=np.float)})
    fluxmap['energies'] = envec
    fluxmap['angles'] = pavec

    xfinal = np.zeros([envec.size, pavec.size, 3])
    vinit = np.zeros([envec.size, pavec.size, 3])
    Einit = np.zeros([envec.size, pavec.size])
    Efinal = np.zeros_like(Einit)

    for icount in range(np.size(res, 0)):
        idex = np.argwhere(res[icount, 4] == envec)
        jdex = np.argwhere(res[icount, 5] == pavec)
        Einit[idex, jdex] = res[icount, 4]
        Efinal[idex, jdex] = res[icount, 6]
        xfinal[idex, jdex, :] = res[icount, 1:4]
        vinit[idex, jdex, :] = res[icount, 7:10]

    fluxmap['init_E'] = Einit
    fluxmap['final_E'] = Efinal
    fluxmap['final_x'] = xfinal
    fluxmap['init_v'] = vinit

    return fluxmap


def energy_to_flux(ei, ef, ec, n, mc2=511.0, kind='kappa', kap=2.5, energyFlux=False):
    """
    Given the particle energy, number density of particles, and characteristic energy of the distribution,
    calculate the differential energy flux in keV-1 cm-2 s-1 sr-1.

    If you are performing backwards tracing from GEO to some point in the tail, Ei is the energy in the tail
    and Ef is the energy at GEO.

    Required Inputs are:
      Ei    Initial energy (energy in source region) in keV
      Ef    Final energy (energy at observation point) in keV
      Ec    Characteristic energy of the distribution in keV (analogous to temperature)
      n     Density of particles in cm-3

    Optional inputs are:
      mc2         Mass energy of the particle species in keV (default is 511 for electrons)
      kind        Type of distribution function to use
                  'kappa'     kappa distribution in energy
                  'maxwell'   relativistic Maxwell-Juttner distribution
      kap         Power law index for the kappa distribution (default is 2.5)
      energyFlux  Whether or not to calculate energy fluxes (default is False)

    The default value of kappa corresponds to electrons in a fairly strong substorm. For other species and
    levels of activity, Gabrielse et al. [2014] provided a table of values for kappa, derived from THEMIS
    observations:

      |AL|    ions    electrons
      min     5.1     2.7
      int     4.6     2.7
      max     4.4     2.5

    Values of n and Ec need to be obtained from some sort of tail plasma model, either kinetic or
    MHD (in which case Ec~P/rho). It is also important to remember that electron temperature usually
    differs from ion temperature, up to a factor of 7 different. It is up to the user to make sure
    that the correct temperature for the desired species is provided.

    Jesse Woodroffe
    3/30/2016
    """

    gami = 1 + ei/mc2
    gamc = 1 + ec/mc2
    gamf = 1 + ef/mc2
    u = ckm*np.sqrt(gami*gami-1.0)/gami
    w = ckm*np.sqrt(gamc*gamc-1.0)/gamc
    v = ckm*np.sqrt(gamf*gamf-1.0)/gamf

    if kind.lower() == 'maxwell':
        # Maxwell-Juttner distribution
        Q = ec/mc2
        f0 = n/(4*np.pi*ckm**3*Q*special.kn(2, 1.0/Q))
        f = f0*np.exp(-gami/Q)
    elif kind.lower() == 'kappa':
        # Kappa distribution
        Wc = ec*(1.0-1.5/kap)
        f0 = n*(mc2/(ckm*ckm*Wc*2*np.pi*kap))**1.5*(special.gamma(kap+1)/special.gamma(kap-0.5))
        f = f0*(1+ei/(kap*Wc))**-(kap+1)
    else:
        raise Exception('Error in energy_to_flux: kind= ' + kind + ' is not supported')

    j = 1e5*ckm*ckm*v*v/mc2*f

    if energyFlux:
        j *= ef

    return j

def calculate_electron_flux(ei,ef,x):

    mc2=511.0

    k1=x[0]
    E1=x[1]
    n1=x[2]
    k2=x[3]
    E2=x[4]
    n2=x[5]

    W1=E1*(1.0-1.5/k1)
    W2=E2*(1.0-1.5/k2)

    # Use gammaln instead of gamma to avoid overflow at large kappa

    kf1 = np.exp(special.gammaln(k1+1)-special.gammaln(k1-0.5))
    g1 = n1*(mc2/(ckm*ckm*W1*np.pi*k1))**1.5*kf1
    f1 = g1*(1+ei/(k1*W1))**-(k1+1)

    kf2 = np.exp(special.gammaln(k2+1)-special.gammaln(k2-0.5))
    g2 = n2*(mc2/(ckm*ckm*W2*np.pi*k2))**1.5*kf2
    f2 = g2*(1+ei/(k2*W2))**-(k2+1)

    gamf = 1+ef/mc2
    v = ckm*np.sqrt(gamf*gamf-1.0)/gamf

    j=1e5*ckm*ckm*v*v/mc2*(f1+f2)

    return j

def calculate_omnidirectional_flux(pav,diffJ,angleDegrees=True,symmetry=True):
    """
    Calculate the omnidirectional flux given differential flux.

    j_omni(E) = int_0^pi int_0^2pi dphi sinQ dQ j_diff(Q,phi,E)
              = 2pi int_0^pi dQ sinQ j_diff(Q,E)


    Inputs:
      pav           1D array of floats   Vector containing pitch angles for each flux value
      diffJ         2D array of floats   Array containg differential fluxes j(a,E)
      angleDegrees  logical,optional     Indicates if pitch angles are in degrees (True) or
                                         radians (set to False). Default is True.
      symmetry      logical,optional     Indicates if distribution is assumed symmetric wrt
                                         direction of magnetic field, so multiplies fluxes by
                                         a factor of two to account for this (basically, this
                                         assumes pitch angles are [0,90]). Default is true.

    Outputs:
      omni          1D array of floats   Vector containing omnidirectional fluxes at each energy.

    Jesse Woodroffe
    6/17/2016

    Modification history:

    8/8/2016    Altered algorithm to allow for non-uniform pitch angle bins

    """

    # Check if array dimensions are reconcilable
    if(not (pav.size in diffJ.shape)):
        raise Exception('Error in calculate_omnidirectional_flux: Dimension mismatch between PAV and DIFFJ')

    # Put angles in radians if necessary
    Q = np.deg2rad(pav) if angleDegrees else pav

    # Transpose the flux array if necessary
    flux = diffJ if pav.size==np.size(diffJ,1) else diffJ.T

    # Integration weight is 2 pi in azimuth times bin widths
    coef = 2.0*np.pi*np.diff(Q)
    if(symmetry): # If assuming directional symmetry, compensate for missing half
        coef*=2.0
    favg=0.5*(flux[:,1:]+flux[:,:-1])
    savg=np.sin(0.5*(Q[1:]+Q[:-1]))

    # Perform the reduction to approximate the integral
    omniJ=np.einsum("i,ji",coef*savg,favg)

    return omniJ

def tm03_moments(x,y,swD,getDefaults=False):
    """
    The Tsyganeko and Mukai [2003] plasma sheet model (with corrected equations).

    Inputs:
      x     GSM x position in Earth radii
      y     GSM y position in Earth radii
      swD   A dictionary with the following keys that must be defined:
          'bperp' Magnitude of the perpendicular component of the solar wind magnetic field in nT
          'theta' Solar wind clock angle in degrees
          'vx'    Solar wind speed in km/s
          'n'     Solar wind density in cm-3
          'p'     Solar wind dynamic pressure in nPa

    Outputs:
      res   A dictionary with the following keys:
          'P'   Local pressure in nPa
          'T'   Local temperature in keV
          'n'   Local ion/electron density in cm-3

    Reference:

    Tsyganeko, N. A. and T. Mukai (2003), Tail plasma sheet models derived from Geotail particle data,
        J. Geophys. Res., 108(A3),1136, doi:10.1029/2002JA009707

    The output from the TM03 model can be used to set n and Ec inputs to the energy_to_flux routine.

    Jesse Woodroffe
    6/2/2016
    """

    if(getDefaults):
      # Create a dictionary with default parameters and return it
      res={}
      res['bperp']=5.0
      res['theta']=90.0
      res['vx']=500.0
      res['n']=10.0
      res['p']=3.0

    else:
      # Evaluate TM03 model using provided parameters
      aT=np.r_[ 0.0000, 1.6780,-0.1606, 1.6690, 4.8200, 2.8550,-0.6020,-0.8360,
               -2.4910, 0.2568, 0.2249, 0.1887,-0.4458,-0.0331,-0.0241,-2.6890,
                1.2220]
      aN=np.r_[ 0.0000,-0.1590, 0.6080, 0.5055, 0.0796, 0.2746, 0.0361,-0.0342,
               -0.7935, 1.1620, 0.4756, 0.7117]
      aP=np.r_[ 0.0000, 0.0570, 0.5240, 0.0908, 0.5270, 0.0780,-4.4220,-1.5330,
               -1.2170, 2.5400, 0.3200, 0.7540, 1.0480,-0.0740, 1.0150]

      bperp=swD['bperp']/5
      bz=swD['bperp']*np.cos(np.deg2rad(swD['theta']))

      if(bz>0):
          bzn=bz/5.0
          bzs=0.0
      else:
          bzn=0.0
          bzs=-bz/5.0

      vsw=swD['vx']/500.0
      nsw=swD['n']/10.0
      fsw=bperp*np.sqrt(np.sin(np.deg2rad(swD['theta'])/2))
      rho=np.sqrt(x*x+y*y)/10.0
      psw=swD['p']/3.0
      phi=-np.arctan2(y,x)
      rm1=rho-1.0

      T=(aT[1]*vsw+aT[2]*bzn+aT[3]*bzs+aT[4]*
         np.exp(-(aT[9]*vsw**aT[15]+aT[10]*bzn+aT[11]*bzs)*rm1)+
         (aT[5]*vsw+aT[6]*bzn+aT[7]*bzs+aT[8]*
          np.exp(-(aT[12]*vsw**aT[16]+aT[13]*bzn+aT[14]*bzs)*rm1))*np.sin(phi)**2)

      N=((aN[1]+aN[2]*nsw**aN[10]+aN[3]*bzn+aN[4]*vsw*bzs)*rho**aN[8]+
         (aN[5]*nsw**aN[11]+aN[6]*bzn+aN[7]*vsw*bzs)*rho**aN[9]*np.sin(phi)**2)

      P=(aP[1]*rho**aP[6]+aP[2]*psw**aP[11]*rho**aP[7]+aP[3]*fsw**aP[12]*rho**aP[8]+
         (aP[4]*psw**aP[13]*np.exp(-aP[9]*rho)+aP[5]*fsw**aP[14]*np.exp(-aP[10]*rho))*np.sin(phi)**2)

      res={'P':P,'T':T,'n':N}

    return res

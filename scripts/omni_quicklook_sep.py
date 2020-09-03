import sys
import os
import glob
import copy
import argparse
import itertools as it
import numpy as np
import spacepy.toolbox as tb
import matplotlib.pyplot as plt

from ptm_python import ptm_tools as ptt
from ptm_python import ptm_postprocessing as post

def calculate_omni(fluxmap, fov=False, initialE=False):
    pp = post.ptm_postprocessor()

    pp.set_source(source_type='kaprel', params=dict(density=5e-6, energy=752.0, kappa=5.0, mass=1847.0))
    # n_dens      float       optional, number density at source region in cm-3
    # e_char      float       optional, characteristic energy of distribution in keV
    # kappa       float       optional, spectral index of kappa distribution
    # mass        float       optional, particle mass in multiples of electron mass
    if initialE:
        fluxmap['final_E'] = fluxmap['init_E']
    diff_flux = pp.map_flux(fluxmap)
    if not initialE:
        nener, nalph = diff_flux.shape
        for idx, jdx in it.product(range(nener), range(nalph)):
            if np.linalg.norm(fluxmap['final_x'][idx, jdx]) >= 14.99:
                continue
            else:
                diff_flux[idx, jdx] = 0.
    if fov:
        angles = instrFOV(fluxmap)
        amask = angles < 90
        diff_flux[amask] = 0.
    omni = pp.get_omni_flux(fluxmap['angles'], diff_flux)

    return omni

def plot_omni(omni, fluxmap):
    fig = plt.figure()
    ax0 = fig.add_axes([0.15, 0.2, 0.78, 0.6])
    en_mev = fluxmap['energies']/1e3
    ax0.loglog(en_mev, omni*1e3, label='Omni')
    enlo, enhi = en_mev[0], en_mev[-1]
    ax0.set_xlabel('Energy [MeV]')
    ax0.set_ylabel('Diff. Flux [per MeV]')
    ax0.set_title(fluxmap.attrs['position'])

    cdict, allow = cutoffs(fluxmap, addTo=ax0, linestyle='--', color='b')
    #ax0.axvline(x=cdict['ec_low'], linestyle=':', color='k',
    #            label='E$_{c}^{low}$ = ' + '{0:.2f} MeV'.format(cdict['ec_low']))
    #ax0.axvline(x=cdict['ec_high'], linestyle=':', color='k',
    #            label='E$_{c}^{high}$ = ' + '{0:.2f} MeV'.format(cdict['ec_high']))

    # a horizontal barcode
    ax1 = fig.add_axes([0.15, 0.05, 0.78, 0.033])
    ax1.set_axis_off()
    #barprops = dict(aspect='auto', cmap='binary', interpolation='nearest')
    barprops = dict(cmap='gray')
    binedges = tb.bin_center_to_edges(en_mev)
    ax1.pcolormesh(np.log10(binedges), np.array([0, 1]),
                   allow[np.newaxis, ...], **barprops)
    enlo, enhi = binedges[0], binedges[-1]
    ax0.set_xlim([enlo, enhi])
    ax1.set_xlim(np.log10([enlo, enhi]))
    return fig, [ax0, ax1]


def cutoffs(fluxmap, addTo=None, **kwargs):
    # find energies where access is forbidden
    if False:  # binary - any access at E or no access
        allow = np.array([True if (np.abs(fluxmap['final_x'][n])==15).any()
                          else False for n in range(len(fluxmap['energies']))])
    else:  # fractional
        allow = np.array([np.sum(np.linalg.norm(fluxmap['final_x'][n], axis=-1) >= 14.99)
                          for n in range(len(fluxmap['energies']))], dtype=np.float)
        allow /= len(fluxmap['angles'])

    en_mev = fluxmap['energies']/1e3
    cdict = dict()
    # Earth (1.1Re to include atmosphere) subtends ~0.225 ster
    # (solid angle = 2*pi*(1-cos(theta)), where theta is angle of inverse
    # position vector to limb of Earth)
    # 0.225 ster/4*pi = 0.179
    not_forbidden = np.nonzero(allow)[0]
    full_access = allow>0.82  # 1-0.18 = 0.82
    idx_low = not_forbidden[0]
    ec_low = en_mev[idx_low]
    print('Ec_low = {}'.format(ec_low))
    # upper cutoff is where all values are "full" transmission
    # Here "full" accounts for solid angle of Earth
    try:
        idx_high = find_runs(full_access)[-1][0]
    except IndexError:
        idx_high = -1
    ec_high = en_mev[idx_high]
    print('Ec_high = {}'.format(ec_high))
    prot_low = ptt.Proton(ec_low)
    prot_high = ptt.Proton(ec_high)

    Nforbid = np.sum(allow*len(fluxmap['angles']))
    Ntot = len(allow)*len(fluxmap['angles'])
    r_low = prot_low.getRigidity()
    r_high = prot_high.getRigidity()
    r_effect = r_low + (r_high-r_low) * Nforbid/Ntot
    cdict['ec_low'] = ec_low
    cdict['r_low'] = r_low
    cdict['ec_high'] = ec_high
    cdict['r_high'] = r_high
    cdict['r_eff'] = r_effect
    cdict['ec_eff'] = ptt.Proton.fromRigidity(r_effect).energy
    if addTo is not None:
        if 'linestyle' not in kwargs:
            kwargs['linestyle'] = '--'
        if 'color' not in kwargs:
            kwargs['color'] = 'b'
        labeltext = 'E$_{c}^{eff}$ = ' + '{0:.2f} MeV'.format(cdict['ec_eff'])\
                    + '\nR$_C$ = ' + '{0:.2f} GV'.format(cdict['r_eff'])
        if 'label_pre' in kwargs:
            labeltext = kwargs['label_pre'] + '\n' + labeltext
        addTo.axvline(x=cdict['ec_eff'], linestyle=kwargs['linestyle'], color=kwargs['color'],
                      label=labeltext)
    return cdict, allow


def find_runs(invec, value=True):
    """Find starts of contiguous blocks"""
    isvalue = np.concatenate(([0], np.equal(invec, value).view(np.int8), [0]))
    absdiff = np.abs(np.diff(isvalue))
    # runs start and end where absdiff is 1
    ranges = np.where(absdiff == 1)[0].reshape(-1, 2)
    return ranges


def add_extra_omni(ax, omni, fluxmap, **kwargs):
    ax.loglog(fluxmap['energies']/1e3, omni*1e3, **kwargs)


def instrFOV(fluxmap):
    # get the instrument field-of-view axis
    # CXD is nadir pointing, so FOW axis is inverse of position vector
    fovaxis = -1*fluxmap.attrs['position']
    fovaxis = fovaxis/np.linalg.norm(fovaxis)
    # get angle between inverse of FOV axis and initial particle velocity
    # (because velocity needs to point in to the detector aperture)
    fiv = fluxmap['init_v']
    angles = np.zeros((fiv.shape[0], fiv.shape[1]))
    for idx in range(fiv.shape[0]):
        for jdx in range(fiv.shape[1]):
            angles[idx, jdx] = np.rad2deg(np.arccos(np.dot(-1*fovaxis, fluxmap['init_v'][idx, jdx]
                                                           /np.linalg.norm(fluxmap['init_v'][idx, jdx]))))
    return angles


if __name__ == '__main__':
    # Set up a basic argument parser
    parser = argparse.ArgumentParser()
    parser.add_argument('dir')
    opt = parser.parse_args()

    fns = glob.glob(os.path.join(opt.dir, 'map_*.dat'))
    fluxmap = ptt.parse_map_file(fns)
    fluxmap_1 = copy.deepcopy(fluxmap)
    fluxmap_2 = copy.deepcopy(fluxmap)
    omni = calculate_omni(fluxmap)
    cdict, allow = cutoffs(fluxmap, addTo=None)
    omni1 = calculate_omni(fluxmap_1, fov=True)
    fig, axes = plot_omni(omni, fluxmap)
    omni2 = calculate_omni(fluxmap_2, initialE=True)
    add_extra_omni(axes[0], omni1, fluxmap_1, label='CXD', color='orange')
    #cdict1, allow1 = cutoffs(fluxmap_1, addTo=axes[0], linestyle='--', color='orange')
    add_extra_omni(axes[0], omni2, fluxmap_2, label='Initial', color='green')
    axes[0].legend()
    ylims = axes[0].get_ylim()
    axes[0].plot(cdict['ec_low'], ylims[0], marker='^', mec='k', mfc='silver', clip_on=False)
    axes[0].plot(cdict['ec_high'], ylims[0], marker='^', mec='k', mfc='grey', clip_on=False)
    axes[0].set_ylim(ylims)
    plt.show()

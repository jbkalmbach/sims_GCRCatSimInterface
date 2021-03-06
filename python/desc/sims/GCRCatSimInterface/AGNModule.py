import numpy as np
import os
import numbers
from lsst.utils import getPackageDir
from lsst.sims.photUtils import Sed, BandpassDict

__all__ = ["log_Eddington_ratio", "M_i_from_L_Mass", "k_correction",
           "tau_from_params", "SF_from_params"]

def log_Eddington_ratio(bhmass, accretion_rate):
    """
    Parameters
    ----------
    bhmass is in solar masses

    accretion_rate is in solar masses per Gyr

    Returns
    -------
    log10(L/L_Eddington)
    """
    # reference for expressions defining Eddington luminosity
    # http://www-astro.physics.ox.ac.uk/~garret/teaching/lecture7-2012.pdf

    log_m_sun = np.log10(1.98855) + 33.0  # in grams
    log_G = np.log10(6.674) - 8.0  # in cgs units
    log_m_proton = log_m_sun - np.log10(1.189) - 57.0  # see A.2 of Kolb and Turner
    log_sigma_T = np.log10(6.6524) - 25.0  # in cm^2 -- A.1.2 of Kolb and Turner
    log_c = np.log10(2.9979) + 10.0  # in cm/sec
    log_sec_per_yr = np.log10(3600.0*24.0*365.25)

    log_Const = np.log10(4.0) + np.log10(np.pi)
    log_Const += log_G + log_c + log_m_proton - log_sigma_T
    log_L_Eddington = np.log10(bhmass) + log_m_sun + log_Const

    log_epsilon = -1.0
    log_L = np.log10(accretion_rate)
    log_L += log_m_sun - 9.0 - log_sec_per_yr
    log_L += log_epsilon
    log_L += 2.0*log_c

    output = log_L-log_L_Eddington
    return output

def M_i_from_L_Mass(Ledd_ratio, bhmass):
    """
    Parameters
    ----------
    Ledd_ratio is the log10(L/L_Eddington) ratio

    bhmass is the log10(mass of the blackhole in solar masses)

    Returns
    -------
    Absolute i-band magnitude.  This will be read off from
    the apparent relationships in Figure 15 of MacLeod et al 2010
    (ApJ, 721, 1014)
    """

    if not hasattr(M_i_from_L_Mass, '_initialized'):
        print('initializing M_i')
        M_i_from_L_Mass._initialized = True

        # example points taken from Figure 15 of MacLeod et al (2010)
        l_edd = [-0.5, -0.5,
                 -0.1, -0.1,
                 -1.1, -1.1,
                 -1.5, -1.5]
        mbh = [9.8, 7.8,
               9.0, 7.7,
               10.1, 8.3,
               10.1, 8.85]
        m_i = [-28.3, -23.2,
               -27.6, -24.4,
               -27.7, -23.2,
               -26.3, -23.1]

        l_edd = np.array(l_edd)
        mbh = np.array(mbh)
        m_i = np.array(m_i)

        theta_best = None
        l_edd_0_best = None
        mbh_0_best = None
        err_best = None
        mm = np.zeros((3,3), dtype=float)
        bb = np.zeros(3, dtype=float)
        nn = len(m_i)

        mm[0][0] = (l_edd**2).sum()
        mm[0][1] = (l_edd*mbh).sum()
        mm[0][2] = l_edd.sum()
        mm[1][0] = mm[0][1]
        mm[1][1] = (mbh**2).sum()
        mm[1][2] = mbh.sum()
        mm[2][0] = l_edd.sum()
        mm[2][1] = mbh.sum()
        mm[2][2] = nn

        bb[0] = (l_edd*m_i).sum()
        bb[1] = (mbh*m_i).sum()
        bb[2] = m_i.sum()

        vv = np.linalg.solve(mm, bb)
        M_i_from_L_Mass._coeffs = vv

    return (M_i_from_L_Mass._coeffs[0]*Ledd_ratio +
            M_i_from_L_Mass._coeffs[1]*bhmass +
            M_i_from_L_Mass._coeffs[2])


def k_correction(sed_obj, bp, redshift):
    """
    Parameters
    ----------
    sed_obj is an instantiation of Sed representing the observed
    spectral energy density of the source

    bp is an instantiation of Bandpass representing the bandpass
    in which we are calculating the magnitudes

    redshift is a float representing the redshift of the source

    Returns
    -------
    K correction in magnitudes according to equation (12) of
    Hogg et al. 2002 (arXiv:astro-ph/0210394)
    """
    if sed_obj.fnu is None:
        sed_obj.flambdaTofnu()

    dilation = 1.0 + redshift

    restframe_wavelen_grid = bp.wavelen*dilation

    if not hasattr(k_correction, '_valid_dex_dict'):
        k_correction._valid_dex_dict = {}

    if bp not in k_correction._valid_dex_dict:
        print('calculating valid dexes')
        valid_bp_dex = np.where(np.abs(bp.sb)>0.0)
        k_correction._valid_dex_dict[bp] = valid_bp_dex

    else:
        valid_bp_dex = k_correction._valid_dex_dict[bp]

    restframe_min_wavelen = restframe_wavelen_grid[valid_bp_dex[0][0]]
    restframe_max_wavelen = restframe_wavelen_grid[valid_bp_dex[0][-1]]

    if (restframe_min_wavelen < sed_obj.wavelen[0] or
        restframe_max_wavelen > sed_obj.wavelen[-1]):

        msg = '\nBP/(1+z) range '
        msg += '%.6e < lambda < %.6e\n' % (restframe_min_wavelen,
                                           restframe_max_wavelen)
        msg += 'SED range '
        mst += '%.6e < lambda < %.6e\n' % (sed_obj.wavelen.min(),
                                           sed_obj.wavelen.max())

        raise RuntimeError(msg)

    restframe_fnu = np.interp(restframe_wavelen_grid,
                              sed_obj.wavelen,
                              sed_obj.fnu,
                              left=0.0,
                              right=0.0)

    observed_fnu = np.interp(bp.wavelen,
                             sed_obj.wavelen,
                             sed_obj.fnu,
                             left=0.0,
                             right=0.0)

    d_wavelen = bp.wavelen[1:]-bp.wavelen[:-1]

    bf_over_w = bp.sb*restframe_fnu/bp.wavelen
    restframe_integral = (0.5*(bf_over_w[1:] + bf_over_w[:-1]) *
                              d_wavelen).sum()

    bf_over_w = bp.sb*observed_fnu/bp.wavelen
    observer_integral = (0.5*(bf_over_w[1:] + bf_over_w[:-1]) *
                             d_wavelen).sum()

    return -2.5*np.log10((1.0+redshift)*observer_integral/restframe_integral)


def tau_from_params(redshift, M_i, mbh, rng=None):
    """
    Use equation (7) and Table 1 (7th row) of MacLeod et al.
    to get tau from black hole parameters

    Parameters
    ----------
    redshift of the black hole (will be used to calculate
    the rest-frame effective wavelength of the i bandpass)

    M_i is the absolute magnitude of the AGN in the i-band

    mbh is the mass of the blackhole in solar masses

    rng is an option np.random.RandomState instantiation
    which will introduce scatter into the coefficients
    of the Macleod et al fit expression

    Returns
    -------
    tau -- the characteristic timescale of the AGN light curve
    in the i-band in days
    """

    if not hasattr(tau_from_params, '_eff_wavelen_i'):
        bp_dict = BandpassDict.loadTotalBandpassesFromFiles()
        eff_wav_nm = bp_dict['i'].calcEffWavelen()
        tau_from_params._eff_wavelen_i = 10.0*eff_wav_nm[0]  # use phi; not sb

    AA = 2.3
    BB = 0.17
    CC = 0.01
    DD = 0.12

    if rng is not None:
        if isinstance(redshift, numbers.Number):
            n_obj = 1
        else:
            n_obj = len(redshift)
        AA += rng.normal(0.0, 0.1, size=n_obj)
        BB += rng.normal(0.0, 0.02, size=n_obj)
        CC += rng.normal(0.0, 0.03, size=n_obj)
        DD += rng.normal(0.0, 0.04, size=n_obj)

    # in Angstroms for i-band
    eff_wavelen = tau_from_params._eff_wavelen_i/(1.0+redshift)

    log_tau = AA + BB*np.log10(eff_wavelen/4000.0)
    log_tau += CC*(M_i+23.0) + DD*(np.log10(mbh)-9.0)
    return np.power(10.0, log_tau)


def SF_from_params(redshift, M_i, mbh, eff_wavelen, rng=None):
    """
    Use equation (7) and Table 1 (2nd row) of MacLeod et al.
    to get the structure function from black hole parameters

    Parameters
    ----------
    redshift of the black hole (will be used to calculate
    the rest-frame effective wavelength of the i bandpass)

    M_i is the absolute magnitude of the AGN in the i-band

    mbh is the mass of the blackhole in solar masses

    eff_wavelen is the observer-frame effective
    wavelength of the band in Angstroms

    rng is an option np.random.RandomState instantiation
    which will introduce scatter into the coefficients
    of the Macleod et al fit expression

    Returns
    -------
    SF -- the structure function of the light curve at infinite
    time lag of at the effective wavelength specified
    """
    AA = -0.56
    BB = -0.479
    CC = 0.111
    DD = 0.11

    if rng is not None:
        if isinstance(redshift, numbers.Number):
            n_obj = 1
        else:
            n_obj = len(redshift)
        AA += rng.normal(0.0, 0.01, size=n_obj)
        BB += rng.normal(0.0, 0.005, size=n_obj)
        CC += rng.normal(0.0, 0.005, size=n_obj)
        DD += rng.normal(0.0, 0.02, size=n_obj)

    eff_wavelen_rest = eff_wavelen/(1.0+redshift)

    log_sf = AA + BB*np.log10(eff_wavelen_rest/4000.0)
    log_sf += CC*(M_i+23.0) + DD*(np.log10(mbh)-9.0)

    return np.power(10.0, log_sf)

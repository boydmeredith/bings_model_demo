"""A one line summary of the module or program, terminated by a period.

Leave one blank line.  The rest of this docstring should contain an
overall description of the module or program.  Optionally, it may also
contain a brief description of exported classes and functions and/or usage
examples.

Typical usage example:

  foo = ClassFoo()
  bar = foo.FunctionBar()
"""

import numpy as np
import scipy as sp




def rate_from_gamma(gamma, total_rate=40):
    """Computes click rates based on gamma and total click rate

    Args:
        gamma: a float representing the log ratio of the right and left click rates
        total_rate: the total click rate in Hz

    Returns:
        left: click rate on the left
        right: click rate on the right
    """
    left = total_rate / (np.exp( gamma) + 1)
    right = total_rate - left
    return left, right


def make_clicktrain(total_rate=40, gamma=1.5, duration=.5, dt=.001, stereo_click=True, rng=1):
    """Generate Poisson Click train

    Args:
        total_rate: total click rate in Hz
        gamma: difficulty (the log ratio of right and left click rates)
        duration: time of stimulus in seconds
        dt: step size for generating clicks in seconds
        stereo_click: whether to use a stereo click
        rng: seed for random number generator

    Returns:
        bups: a dict containing left and right clicks and other information about the click train
    """

    tvec = np.arange(0, duration, dt)
    left_rate, right_rate = rate_from_gamma(gamma, total_rate)
    left_rate = total_rate - right_rate

    np.random.seed(rng)
    right_ind = np.random.random_sample(np.shape(tvec)) < (right_rate * dt)
    left_ind = np.random.random_sample(np.shape(tvec)) < (left_rate * dt)

    if stereo_click:
        first_ind = np.argwhere(right_ind+left_ind>0)[0]
        right_ind[first_ind] = 1
        left_ind[first_ind] = 1

    left_bups = tvec[left_ind]
    right_bups = tvec[right_ind]

    bups = {'left':left_bups, 'right':right_bups, 'tvec':tvec,
        'right_ind':right_ind, 'left_ind':left_ind, 'duration':duration,
           'left_rate':left_rate, 'right_rate':right_rate}

    return bups

def make_adapted_clicks(bups, phi=.1, tau_phi=.2, cross_stream=True):
    """Apply adaptation process to click train and record in bups

    Args:
        bups: a dict containing left, right, left_rate, right_rate and duration
        phi: adaptation intensity
        tau_phi: timescale of adaptation
        cross_stream: whether to apply cross stream adaptation

    Returns:
        None
    """

    if not cross_stream:
        raise notImplementedError
    if phi > 1:
        raise notImplementedError

    # concatenate left and right bups to get interclick intervals
    left_bups = bups['left']
    right_bups = bups['right']
    bups_cat = np.hstack([left_bups, right_bups])
    sign_cat = np.hstack([-np.ones_like(left_bups), np.ones_like(right_bups)])
    sort_order = np.argsort(bups_cat)
    bups_cat = bups_cat[sort_order]
    sign_cat = sign_cat[sort_order]
    C = adapt_clicks(phi, tau_phi, bups_cat)

    left_adapted = C[sign_cat==-1]
    right_adapted = C[sign_cat==1]
    bups['left_adapted'] = left_adapted
    bups['right_adapted'] = right_adapted

    # compute the full adaptation process
    tvec, Cfull = compute_full_adaptation(bups, phi, tau_phi)
    bups['Cfull'] = Cfull
    bups['tvec'] = tvec
    return None

def adapt_clicks(phi, tau_phi, bups_cat):
    ici = np.diff(bups_cat)
    C  = np.ones_like(bups_cat)
    cross_side_suppression = 0
    for ii in np.arange(1,len(C)):
        if ici[ii-1] <= cross_side_suppression and phi != 1:
            C[ii-1] = 0
            C[ii] = 0
            continue
        if abs(phi-1) > 1e-5:
            adapt_ici(phi, tau_phi, ici, C, ii, style='bing')
    return C

def integrate_adapted_clicks(bups, lam=0, s2s=0.001, s2a=.001, s2i=.001, bias=0, B=5., nagents=5, rng=1):
    """Apply integration process to adapted click train in bups

    Args:
        bups: a dict containing left, right, left_rate, right_rate and duration
        lam: adaptation intensity
        s2s:
        s2a:
        s2i:
        bias:
        B:
        nagents:

    Returns:
        None
    """
    params = {"bias" : bias, "B" : B}
    np.random.seed(rng)
    tvec = bups['tvec']
    dt = np.mean(np.diff(tvec))
    dur = bups['duration']

    left_adapted = bups['left_adapted'].copy()
    right_adapted = bups['right_adapted'].copy()
    left_ts = bups['left']
    right_ts = bups['right']
    left_adapted *= np.exp(lam * (dur - left_ts))
    right_adapted *= np.exp(lam * (dur - right_ts))
    a_agents = np.zeros([nagents, len(tvec)])
    for agenti in np.arange(nagents):
        left_vals = np.zeros_like(tvec)
        right_vals = np.zeros_like(tvec)

        left_vals[bups['left_ind']] =  left_adapted
        right_vals[bups['right_ind']] = right_adapted
        difflr = -left_vals + right_vals
        sumlr = left_vals + right_vals

        init_noise = np.random.normal(loc=0, scale=np.sqrt(s2i))
        a = np.zeros_like(tvec) + init_noise
        for ii in np.arange(len(tvec)-1):
            last_a = a[ii]

            adot = (dt * lam * last_a +
                    difflr[ii] +
                    np.random.normal(scale=np.sqrt(sumlr[[ii]]*s2s)) +
                    np.random.normal(scale=np.sqrt(s2a*dt)))
            a[ii+1] = last_a + adot

        crossing = np.argwhere(abs(a)>B)
        if len(crossing ) > 0:
            ii = crossing[0][0]
            a[ii:] = np.ones_like(a[ii:])*np.sign(a[ii])*B
        a_agents[agenti, :] = a
    return a_agents, params

def compute_full_adaptation(bups, phi, tau_phi):
    tvec = bups['tvec']
    dt = np.mean(np.diff(tvec))
    Cfull = np.ones_like(tvec)

    for (ii, tt) in enumerate(tvec[:-1]):
        thislb = bups['left_ind'][ii] * 1.
        thisrb = bups['right_ind'][ii] * 1.
        if thislb + thisrb == 2. and phi != 1:
            Cfull[ii] = 0
        Cdot =  (1-Cfull[ii]) / tau_phi * dt + (phi - 1) * Cfull[ii] * (thislb + thisrb)
        Cfull[ii+1] = Cfull[ii] + Cdot
    return tvec,Cfull

def adapt_ici(phi, tau_phi, ici, C, ii, style='bing'):
    if style=='bing':
        last = tau_phi  * np.log(abs(1 - C[ii-1] * phi))
        C[ii] = 1 - np.exp((-ici[ii-1] + last) / tau_phi)
    if style=='brian':
        arg = (1/tau_phi) * (-ici[ii-1] + sp.special.xlogy(tau_phi, abs(1.-C[ii-1]*phi)))
        if C[ii]*phi <=1:
            C[ii] = 1. - np.exp(arg)
        else:
            C[ii] = 1. + np.exp(arg)

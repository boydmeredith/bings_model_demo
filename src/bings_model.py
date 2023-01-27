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
import matplotlib.pyplot as plt
import seaborn as sns

left_color = "purple"
right_color = "green"


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

    left_adapted = C[sign_cat==-1]
    right_adapted = C[sign_cat==1]
    bups['left_adapted'] = left_adapted
    bups['right_adapted'] = right_adapted

    # compute the full adaptation process
    tvec, Cfull = compute_full_adaptation(bups, phi, tau_phi)
    bups['Cfull'] = Cfull
    bups['tvec'] = tvec
    return None

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

##########
# Plotting code
##########

def plot_process(bups, a, params):
    """
    Create a figure summarizing accumulation process

    Draw four panels.
    1. The left and right click events
    2. The sensory adaptation process that determines each click's impact on the accumulator value (before sensory noise is applied)
    3. The magnitide of each click after sensory adaptation 
    4. Realizations the accumulation process

    Args:
        bups: A dictionary containing information about the click train and adaptation process
        a: An N X T numpy array containing N realizations at T timepoint 
        params: The agent's accumulation parameters
    
    Returns:
        fig: A figure containing each of the subplots 

    """
    fig, ax = plt.subplots(4,1, sharex=True, 
                           figsize=(6,7),
                           gridspec_kw={'height_ratios': [.2, .2, .45, 1]})
    
    plot_clicktrain(bups, ax=ax[0])
    ax[0].set_ylabel('')
    ax[0].spines[['left','bottom']].set_linewidth(0)
    ax[0].axes.get_xaxis().set_visible(False)
    ax[0].tick_params(left=False)
        
    plot_adaptation_process(bups, ax=ax[1])
    ax[1].set_xlabel('')
    ax[1].axes.get_xaxis().set_visible(False)
    ax[1].spines[['left']].set_linewidth(0)
    
    plot_adapted_clicks(bups, ax=ax[2])
    ax[2].axes.get_xaxis().set_visible(False)
    ax[2].spines[['bottom']].set_visible(False)
    ax[2].spines[['left']].set_linewidth(0)
    ax[2].spines[['bottom']].set_linewidth(.5)

    
    plot_accumulation(bups, a, params, ax=ax[3])
    
    fig.tight_layout()
    ax[0].set_xlim([-.025, bups['duration']+.025])
    #fig.align_ylabels()
    plt.show()
    return fig


def plot_clicktrain(bups, ax=[]):
    """Creates a figure containing a plot of the left and right clicks

    Args:
        bups: a dict containing left, right, left_rate, right_rate and duration

    Returns:
        None
    """
    if ax==[]:
        fig, ax = plt.subplots( figsize=(4,1.75))
        
    left_bups, right_bups = bups['left'], bups['right']
    left_rate, right_rate = bups['left_rate'], bups['right_rate']
    duration = bups['duration']
    
    ax.eventplot(left_bups,lineoffsets=-.5,color=left_color, alpha=.5)
    ax.eventplot(right_bups,lineoffsets=.5,color=right_color, alpha=.5)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Click sign")
    ax.set_title(f"Clicks $(r_L={left_rate:.2f}$ Hz, $r_R={right_rate:.2f}$ Hz)" )
    ax.set_xlim([0, duration])
    ax.set_yticks([-1, 1])
    ax.set_yticklabels([r'$\delta_L$',r'$\delta_R$'])
    return None

def plot_adaptation_process(bups, ax=[]):
    ms = 4
    alpha = .3
    if ax == []:
        print('no axes supplied')
        fig, ax = plt.subplots(figsize=(4,2))
        
    left_bups, right_bups = bups['left'], bups['right']
    tvec, Cfull = bups['tvec'], bups['Cfull']
    Cmax = np.percentile(Cfull, 99.5)
    
    ax.plot(tvec, Cfull, color = "gray")
    #ax.plot(left_bups, np.ones_like(left_bups) * Cmax, "o", color=left_color, alpha=alpha, ms=ms)
    #ax.plot(right_bups, np.ones_like(right_bups) * Cmax, "o", color=right_color, alpha=alpha, ms=ms)
    ax.set_title("Adaptation process")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("C")
    ax.set_ylim([0, Cmax*1.1])
    
def plot_adapted_clicks(bups, ax=[]):
    ms = 4
    alpha = .3
    if ax == []:
        fig, ax = plt.subplots(figsize=(4,2))
        
    left_bups, right_bups = bups['left'], bups['right']
    left_adapted, right_adapted = bups['left_adapted'], bups['right_adapted']
    ymax = max(np.hstack([left_adapted, right_adapted]))*1.1
    yl = [-ymax, ymax]
    #yl = [-1, 1]
    ax.plot(np.vstack([left_bups, left_bups]),
             np.vstack([np.zeros_like(left_bups), -left_adapted]), color=left_color, alpha=2*alpha)
    ax.plot(np.vstack([right_bups, right_bups]),
             np.vstack([np.zeros_like(right_bups), right_adapted]), color=right_color, alpha=2*alpha)

    ax.plot(left_bups,-left_adapted, "o", color=left_color, alpha=alpha, ms=ms)
    ax.plot(right_bups,right_adapted, "o", color=right_color, alpha=alpha, ms=ms)
    ax.set_xlabel("Time (s)")
    ax.set_title("Adapted clicks")
    ax.set_ylabel(r"$C \cdot \delta_{R,L}$")
    ax.set_ylim(yl)
    ax.spines['bottom'].set_position(('data',0))

    plt.tight_layout()


def plot_accumulation(bups, a_agents, params, ax=[]):
    tvec, dur = bups['tvec'], bups['duration']
    bias, B = params['bias'], params['B']
    if ax == []:
        fig, ax = plt.subplots(figsize=(4,2))
    alims = [-1, 1]
    ax.set_xlim([0, dur])
    ax.axhline(bias,color='black',linestyle=':')
    ax.axhline(B,color='black',linestyle='-',lw=1)
    ax.axhline(-B,color='black',linestyle='-',lw=1)
    for a in a_agents:
        ax.plot(tvec, a, color="pink")
        alims[0] = min(alims[0],np.min(a)*1.1)
        alims[1] = max(alims[1],np.max(a)*1.1)
    ax.set_ylim(alims)
    ax.set_xlabel("Time (s)")
    ax.set_title("Accumulation process")
    ax.set_ylabel("a")
    sns.despine()

def plot_choices(a_agents, bias=0, lapse=0):
    a = a_agents[:,-1]
    nagents = len(a)
    go_right = a > bias
    is_lapse = np.random.random_sample(len(a)) < lapse
    go_right[is_lapse] = np.random.random_sample(sum(is_lapse)) < .5
    ngoright = sum(go_right)
    nlapses = sum(is_lapse)

    fig, ax = plt.subplots(figsize=(4,2))
    ax.scatter(a[~is_lapse], go_right[~is_lapse], label= "non-lapse", alpha=.5)
    ax.scatter(a[is_lapse], go_right[is_lapse], label = "lapse", alpha=.5)
    xl = np.array(ax.get_xlim())
    xl[0] = min(xl[0], bias-.5)
    xl[1] = max(xl[1], bias+.5)
    ax.plot([xl[0],bias], np.ones(2)*lapse/2, color="gray", label="P(go right)")
    ax.plot([bias,xl[1]], 1-np.ones(2)*lapse/2, color="gray")
    ax.plot([bias, bias], [lapse/2, 1-lapse/2], color="gray", linestyle="--")
    ax.set_xlabel("Accumulation value, a")
    ax.set_ylabel("P(go right)")
    ax.legend(loc='upper center', ncol=3, bbox_to_anchor=(.5 ,1.5))
    #display(f'{ngoright}/{nagents} realizations chose right; {nlapses} lapse trials')
    

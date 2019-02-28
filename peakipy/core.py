""" Functions for NMR peak deconvolution """
from pathlib import Path

import numpy as np
import nmrglue as ng
import matplotlib.pyplot as plt

from numpy import sqrt, log, pi, exp
from scipy import stats
from lmfit import Model, report_fit
from mpl_toolkits.mplot3d import Axes3D
from matplotlib.cm import viridis


# constants
log2 = log(2)
s2pi = sqrt(2 * pi)
spi = sqrt(pi)

π = pi
# √π = sqrt(π)
# √2π =  sqrt(2*π)

s2 = sqrt(2.0)
tiny = 1.0e-13


def gaussian(x, amplitude=1.0, center=0.0, sigma=1.0):
    """Return a 1-dimensional Gaussian function.
    gaussian(x, amplitude, center, sigma) =
        (amplitude/(s2pi*sigma)) * exp(-(1.0*x-center)**2 / (2*sigma**2))
    """
    return (amplitude / (sqrt(2 * π) * sigma)) * exp(
        -(1.0 * x - center) ** 2 / (2 * sigma ** 2)
    )


def lorentzian(x, amplitude=1.0, center=0.0, sigma=1.0):
    """Return a 1-dimensional Lorentzian function.
    lorentzian(x, amplitude, center, sigma) =
        (amplitude/(1 + ((1.0*x-center)/sigma)**2)) / (pi*sigma)
    """
    return (amplitude / (1 + ((1.0 * x - center) / sigma) ** 2)) / (π * sigma)


#def pvoigt2d(
#    XY,
#    amplitude=1.0,
#    center_x=0.5,
#    center_y=0.5,
#    sigma_x=1.0,
#    sigma_y=1.0,
#    fraction=0.5,
#):
#    """ 2D pseudo-voigt model
#
#        Arguments:
#            -- XY: meshgrid of X and Y coordinates [X,Y] each with shape Z
#            -- amplitude: peak amplitude (gaussian and lorentzian)
#            -- center_x: position of peak in x
#            -- center_y: position of peak in y
#            -- sigma_x: linewidth in x
#            -- sigma_y: linewidth in y
#            -- fraction: fraction of lorenztian in fit
#
#        Returns:
#            -- flattened array of Z values (use Z.reshape(X.shape) for recovery)
#
#    """
#    x, y = XY
#    sigma_gx = sigma_x / sqrt(2 * log2)
#    sigma_gy = sigma_y / sqrt(2 * log2)
#    # fraction same for both dimensions
#    # super position of gaussian and lorentzian
#    # then convoluted for x y
#    pv_x = (1 - fraction) * gaussian(
#        x, amplitude, center_x, sigma_gx
#    ) + fraction * lorentzian(x, amplitude, center_x, sigma_x)
#    pv_y = (1 - fraction) * gaussian(
#        y, amplitude, center_y, sigma_gy
#    ) + fraction * lorentzian(y, amplitude, center_y, sigma_y)
#    return pv_x * pv_y

def pvoigt2d(
    XY,
    amplitude=1.0,
    center_x=0.5,
    center_y=0.5,
    sigma_x=1.0,
    sigma_y=1.0,
    fraction=0.5,
):
    """ 2D pseudo-voigt model

        Arguments:
            -- XY: meshgrid of X and Y coordinates [X,Y] each with shape Z
            -- amplitude: peak amplitude (gaussian and lorentzian)
            -- center_x: position of peak in x
            -- center_y: position of peak in y
            -- sigma_x: linewidth in x
            -- sigma_y: linewidth in y
            -- fraction: fraction of lorenztian in fit

        Returns:
            -- flattened array of Z values (use Z.reshape(X.shape) for recovery)

    """
    def gaussian(x, center=0.0, sigma=1.0):
        """Return a 1-dimensional Gaussian function.
        gaussian(x, center, sigma) =
            (1/(s2pi*sigma)) * exp(-(1.0*x-center)**2 / (2*sigma**2))
        """
        return (1.0 / (sqrt(2 * π) * sigma)) * exp(
            -(1.0 * x - center) ** 2 / (2 * sigma ** 2)
        )


    def lorentzian(x, center=0.0, sigma=1.0):
        """Return a 1-dimensional Lorentzian function.
        lorentzian(x, center, sigma) =
            (1/(1 + ((1.0*x-center)/sigma)**2)) / (pi*sigma)
        """
        return (1.0 / (1 + ((1.0 * x - center) / sigma) ** 2)) / (π * sigma)

    x, y = XY
    sigma_gx = sigma_x / sqrt(2 * log2)
    sigma_gy = sigma_y / sqrt(2 * log2)
    # fraction same for both dimensions
    # super position of gaussian and lorentzian
    # then convoluted for x y
    pv_x = (1 - fraction) * gaussian(
        x, center_x, sigma_gx
    ) + fraction * lorentzian(x, center_x, sigma_x)
    pv_y = (1 - fraction) * gaussian(
        y, center_y, sigma_gy
    ) + fraction * lorentzian(y, center_y, sigma_y)
    return amplitude * pv_x * pv_y


def make_mask(data, c_x, c_y, r_x, r_y):
    """ Create and elliptical mask

        ToDo:
            write explanation of function

        Arguments:
            data -- 2D array
            c_x  -- x center
            c_y  -- y center
            r_x  -- radius in x
            r_y  -- radius in y

        Returns:
            boolean mask of data.shape


    """
    a, b = c_y, c_x
    n_y, n_x = data.shape
    y, x = np.ogrid[-a : n_y - a, -b : n_x - b]
    mask = x ** 2.0 / r_x ** 2.0 + y ** 2.0 / r_y ** 2.0 <= 1.0
    return mask


# ERROR CALCULATION
def r_square(data, residuals):
    """ Calculate R^2 value for fit

        Arguments:
            data -- array of data used for fitting
            residuals -- residuals for fit

        Returns:
            R^2 value
    """
    SS_tot = np.sum((data - data.mean()) ** 2.0)
    SS_res = np.sum(residuals ** 2.0)
    r2 = 1 - SS_res / SS_tot
    return r2

def rmsd(residuals):
    return np.sqrt(np.sum(residuals ** 2.)/ len(residuals))

def fix_params(params, to_fix):
    """ Set parameters to fix

        Arguments:
             -- params: lmfit parameters
             -- to_fix: parameter name to fix

        Returns:
            -- params: updated parameter object
    """
    for k in params:
        for p in to_fix:
            if p in k:
                params[k].vary = False

    return params


def get_params(params, name):
    ps = []
    ps_err = []
    names = []
    for k in params:
        if name in k:
            ps.append(params[k].value)
            ps_err.append(params[k].stderr)
            names.append(k)
    return ps, ps_err, names


def make_param_dict(peaks, data, lineshape="PV"):
    """ Make dict of parameter names using prefix """

    param_dict = {}

    for index, peak in peaks.iterrows():

        str_form = lambda x: "%s%s" % (to_prefix(peak.ASS), x)
        # using exact value of points (i.e decimal)
        param_dict[str_form("center_x")] = peak.X_AXISf
        param_dict[str_form("center_y")] = peak.Y_AXISf
        param_dict[str_form("sigma_x")] = peak.XW / 2.0
        param_dict[str_form("sigma_y")] = peak.YW / 2.0
        # estimate peak volume
        amplitude_est = data[
            int(peak.Y_AXIS) - int(peak.YW) : int(peak.Y_AXIS) + int(peak.YW) + 1,
            int(peak.X_AXIS) - int(peak.XW) : int(peak.X_AXIS) + int(peak.XW) + 1,
        ].sum()

        ## in case of negative amplitudes
        #if amplitude_est < 0.0:
        #    amplitude_est = -1.0 * np.sqrt(abs(amplitude_est))
        #else:
        #    amplitude_est = np.sqrt(amplitude_est)

        param_dict[
            str_form("amplitude")
        ] = amplitude_est  # since A is sqrt of actual amplitude
        if lineshape == "G":
            param_dict[str_form("fraction")] = 0.0
        elif lineshape == "L":
            param_dict[str_form("fraction")] = 1.0
        else:
            param_dict[str_form("fraction")] = 0.5

    return param_dict


def to_prefix(x):
    prefix = "_" + x
    to_replace = [[" ", ""], ["{", "_"], ["}", "_"], ["[", "_"], ["]", "_"],["-",""],["/","or"],["?","maybe"],["\\",""]]
    for p in to_replace:
        prefix = prefix.replace(*p)
    #print("prefix", prefix)
    return prefix + "_"


def make_models(model, peaks, data, lineshape="PV"):
    """ Make composite models for multiple peaks

        Arguments:
            -- models
            -- peaks: list of Peak objects [<Peak1>,<Peak2>,...]
            -- lineshape: PV/G/L

        Returns:
            -- mod: Composite model containing all peaks
            -- p_guess: params for composite model with starting values

        Maybe add mask making to this function
    """
    if len(peaks) == 1:
        # make model for first peak
        mod = Model(model, prefix="%s" % to_prefix(peaks.ASS.iloc[0]))
        # add parameters
        param_dict = make_param_dict(peaks, data, lineshape=lineshape)
        p_guess = mod.make_params(**param_dict)

    elif len(peaks) > 1:
        # make model for first peak
        first_peak, *remaining_peaks = peaks.iterrows()
        mod = Model(model, prefix="%s" % to_prefix(first_peak[1].ASS))
        for index, peak in remaining_peaks:
            mod += Model(model, prefix="%s" % to_prefix(peak.ASS))

        param_dict = make_param_dict(peaks, data, lineshape=lineshape)
        p_guess = mod.make_params(**param_dict)
        # add Peak params to p_guess

    update_params(p_guess, param_dict, lineshape=lineshape)

    return mod, p_guess


def update_params(params, param_dict, lineshape="PV"):
    """ Update lmfit parameters with values from Peak

        Arguments:
             -- params: lmfit parameter object
             -- peaks: list of Peak objects that parameters correspond to

        ToDo:
             -- deal with boundaries
             -- currently positions in points
             --

    """
    for k, v in param_dict.items():
        params[k].value = v
        #print("update", k, v)
        if "center" in k:
            #params[k].min = v - 5
            #params[k].max = v + 5
            pass
            #print(
            #    "setting limit of %s, min = %.3e, max = %.3e"
            #    % (k, params[k].min, params[k].max)
            #)
        elif "sigma" in k:
            params[k].min = 0.0
            params[k].max = 1e4
            #print(
            #    "setting limit of %s, min = %.3e, max = %.3e"
            #    % (k, params[k].min, params[k].max)
            #)
        elif "fraction" in k:
            # fix weighting between 0 and 1
            params[k].min = 0.0
            params[k].max = 1.0

            if lineshape == "G":
                params[k].vary = False
            elif lineshape == "L":
                params[k].vary = False

    # return params


def fit_first_plane(
    group,
    data,
    uc_dics,
    noise=None,
    lineshape="PV",
    plot=None,
    show=True,
    verbose=False,
):
    """
        Arguments:

            group -- pandas data from containing group of peaks
            data  -- 
            uc_dics -- unit conversion dics
            plot -- if True show wireframe plots

        To do:
            add model selection
    
    """

    mask = np.zeros(data.shape, dtype=bool)
    mod, p_guess = make_models(pvoigt2d, group, data, lineshape=lineshape)
    # print(p_guess)
    # get initial peak centers
    cen_x = [p_guess[k].value for k in p_guess if "center_x" in k]
    cen_y = [p_guess[k].value for k in p_guess if "center_y" in k]

    for index, peak in group.iterrows():
        #  minus 1 from X_AXIS and Y_AXIS to center peaks in mask
        # print(peak.X_AXIS,peak.Y_AXIS,row.HEIGHT)
        mask += make_mask(data, peak.X_AXISf, peak.Y_AXISf, peak.X_RADIUS, peak.Y_RADIUS)
        # print(peak)

    # needs checking since this may not center peaks
    x_radius = group.X_RADIUS.max()
    y_radius = group.Y_RADIUS.max()
    max_x, min_x = int(round(max(cen_x))) + x_radius, int(round(min(cen_x))) - x_radius
    max_y, min_y = int(round(max(cen_y))) + y_radius, int(round(min(cen_y))) - y_radius

    peak_slices = data.copy()[mask]

    # must be a better way to make the meshgrid
    x = np.arange(1, data.shape[-1] + 1)
    y = np.arange(1, data.shape[-2] + 1)
    XY = np.meshgrid(x, y)
    X, Y = XY

    XY_slices = [X.copy()[mask], Y.copy()[mask]]
    out = mod.fit(
        peak_slices, XY=XY_slices, params=p_guess
    )  # , weights=weights[mask].ravel())
    if verbose:
        print(out.fit_report())
    #print(p_guess)

    # calculate chi2 
    Zsim = mod.eval(XY=XY, params=out.params)
    Zsim[~mask] = np.nan
    Z_plot = data.copy()
    Z_plot[~mask] = np.nan

    norm_z = (Z_plot - np.nanmin(Z_plot)) / (np.nanmax(Z_plot) - np.nanmin(Z_plot))
    norm_sim = (Zsim - np.nanmin(Z_plot)) / (np.nanmax(Z_plot) - np.nanmin(Z_plot))
    _norm_z = norm_z[~np.isnan(norm_z)]
    _norm_sim = norm_sim[~np.isnan(norm_sim)]
    chi2 = np.sum((_norm_z - _norm_sim)**2. / _norm_sim)

    if chi2 < 1:
        print(f"Cluster {peak.CLUSTID} - chi2={chi2:.3f} - ")
    else:
        print(f"Cluster {peak.CLUSTID} - chi2={chi2:.3f} - NEEDS CHECKING")
    

    if plot != None:
        plot_path = Path(plot)
        Zsim = mod.eval(XY=XY, params=out.params)
        #print(report_fit(out.params))
        Zsim[~mask] = np.nan

        # plotting
        fig = plt.figure()
        ax = fig.add_subplot(111, projection="3d")
        Z_plot = data.copy()
        Z_plot[~mask] = np.nan
        # convert to ints may need tweeking
        min_x = int(np.floor(min_x))
        max_x = int(np.ceil(max_x))
        min_y = int(np.floor(min_y))
        max_y = int(np.ceil(max_y))
        X_plot = uc_dics["f2"].ppm(X[min_y - 1 : max_y, min_x - 1 : max_x])
        Y_plot = uc_dics["f1"].ppm(Y[min_y - 1 : max_y, min_x - 1 : max_x])
        Z_plot = Z_plot[min_y - 1 : max_y, min_x - 1 : max_x]
        Zsim = Zsim[min_y - 1 : max_y, min_x - 1 : max_x]

        # calculate chi2 
        norm_z = (Z_plot - np.nanmin(Z_plot)) / (np.nanmax(Z_plot) - np.nanmin(Z_plot))
        norm_sim = (Zsim - np.nanmin(Z_plot)) / (np.nanmax(Z_plot) - np.nanmin(Z_plot))
        _norm_z = norm_z[~np.isnan(norm_z)]
        _norm_sim = norm_sim[~np.isnan(norm_sim)]
        chi2 = np.sum((_norm_z - _norm_sim)**2. / _norm_sim)

        ax.set_title("$\chi^2$="+f"{chi2:.3f}")
        #contf = ax.contourf(X_plot,Y_plot,residuals,100,zdir='z',cmap=viridis, alpha=0.75)

        # plot raw data
        ax.plot_wireframe(
            X_plot, Y_plot, Z_plot, color="k"
            #X_plot, Y_plot, norm_z, color="k"
        )
        # ax.contour3D(X_plot, Y_plot, Z_plot[min_y - 1 : max_y, min_x - 1 : max_x],cmap='viridis')

        ax.set_xlabel("F2 ppm")
        ax.set_ylabel("F1 ppm")
        #ax.set_title("$R^2=%.3f$" % r_square(peak_slices.ravel(), out.residual))
        #cmap = [tuple(i) for i in viridis(np.ravel(np.sqrt((Z_plot-Zsim)**2.)))]
        ax.plot_wireframe(
            X_plot,
            Y_plot,
            Zsim,
            #norm_sim,
            colors='r',
            linestyle="--",
            label="fit",
        )
        ax.invert_xaxis()
        ax.invert_yaxis()
        # Annotate plots
        labs = []
        Z_lab = []
        Y_lab = []
        X_lab = []
        for k, v in out.params.valuesdict().items():
            if "amplitude" in k:
                Z_lab.append(v)
                # get prefix
                labs.append(" ".join(k.split("_")[:-1]))
            elif "center_x" in k:
                X_lab.append(uc_dics["f2"].ppm(v))
            elif "center_y" in k:
                Y_lab.append(uc_dics["f1"].ppm(v))
        #  this is dumb as !£$@
        Z_lab = [
            data[
                int(round(uc_dics["f1"](y, "ppm"))), int(round(uc_dics["f2"](x, "ppm")))
            ]
            for x, y in zip(X_lab, Y_lab)
        ]

        for l, x, y, z in zip(labs, X_lab, Y_lab, Z_lab):
            # print(l, x, y, z)
            ax.text(x, y, z * 1.4, l, None)

        #plt.colorbar(contf)
        plt.legend()

        name = group.CLUSTID.iloc[0]
        if show:
            plt.savefig(plot_path / f"{name}.png", dpi=300)
            plt.show()
        else:
            plt.savefig(plot_path / f"{name}.png", dpi=300)
        #    print(p_guess)
        # close plot
        plt.close()
    return out, mask

class Pseudo3D:
    """ Read dic, data from NMRGlue and dims from input to create a 
        Pseudo3D dataset

        Arguments:
            dic  -- dic from nmrglue.pipe.read
            data -- data from nmrglue.pipe.read
            dims -- dimension order i.e [0,1,2]
                    0 = planes, 1 = f1, 2 = f2

        Methods:

            
    """
    def __init__(self, dic, data, dims):
        # check dimensions
        self._udic = ng.pipe.guess_udic(dic, data)
        self._ndim = self._udic['ndim']

        if self._ndim == 1:
            raise TypeError("NMR Data should be either 2D or 3D")

        elif (self._ndim == 2) and (len(dims)==2):
            self._f1_dim, self._f2_dim = dims
            self._planes = 0
            self._uc_f1 = ng.pipe.make_uc(dic, data, dim=self._f1_dim)
            self._uc_f2 = ng.pipe.make_uc(dic, data, dim=self._f2_dim)
            # make data pseudo3d
            self._data = data.reshape((1, data.shape[0], data.shape[1]))
            self._dims = [self._planes, self._f1_dim+1, self._f2_dim+1]

        else:
            self._planes, self._f1_dim, self._f2_dim = dims
            self._dims = dims
            self._data = data
            # make unit conversion dicts
            self._uc_f2 = ng.pipe.make_uc(dic, data, dim=self._f2_dim)
            self._uc_f1 = ng.pipe.make_uc(dic, data, dim=self._f1_dim)

        #  rearrange data if dims not in standard order
        if self._dims != [0, 1, 2]:
            self._data = np.transpose(data, self._dims)

        self._dic = dic

    @property
    def uc_f1(self):
        """ Return unit conversion dict for F1"""
        return self._uc_f1

    @property
    def uc_f2(self):
        """ Return unit conversion dict for F2"""
        return self._uc_f2

    @property
    def dims(self):
        """ Return dimension order """
        return self._dims

    @property
    def data(self):
        """ Return array containing data """
        return self._data

    @property
    def dic(self):
        return self._dic

    @property
    def udic(self):
        return self._udic

    @property
    def ndim(self):
        return self._ndim

    # size of f1 and f2 in points
    @property
    def f2_size(self):
        """ Return size of f2 dimension in points """
        return self._udic[self._f2_dim]["size"]

    @property
    def f1_size(self):
        """ Return size of f1 dimension in points """
        return self._udic[self._f1_dim]["size"]

    # points per ppm
    @property
    def pt_per_ppm_f1(self):
        return self.f1_size / (self._udic[self._f1_dim]["sw"] / self._udic[self._f1_dim]["obs"]) 

    @property
    def pt_per_ppm_f2(self):
        return self.f2_size / (self._udic[self._f2_dim]["sw"] / self._udic[self._f2_dim]["obs"]) 

    # points per hz 
    @property
    def pt_per_hz_f1(self):
        return self.f1_size / self._udic[self._f1_dim]["sw"] 

    @property
    def pt_per_hz_f2(self):
        return self.f2_size / self._udic[self._f2_dim]["sw"]

    # ppm per point
    @property
    def ppm_per_pt_f1(self):
        return 1. / self.pt_per_ppm_f1

    @property
    def ppm_per_pt_f2(self):
        return 1. / self.pt_per_ppm_f2

    # get ppm limits for ppm scales
#    uc_f1 = ng.pipe.make_uc(dic, data, dim=f1)
#    ppm_f1 = uc_f1.ppm_scale()
#    ppm_f1_0, ppm_f1_1 = uc_f1.ppm_limits()
#
#    uc_f2 = ng.pipe.make_uc(dic, data, dim=f2)
#    ppm_f2 = uc_f2.ppm_scale()
#    ppm_f2_0, ppm_f2_1 = uc_f2.ppm_limits()
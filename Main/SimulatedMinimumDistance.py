#####################################################################
# Source: https://www.dropbox.com/s/g1im7uqzukvqo53/web_sens.zip?dl=0
# Thanks to Thomas Jørgensen for sharing the code
#####################################################################

# global modules
import numpy as np
import time
import scipy as sci
from scipy.optimize import minimize
import pickle
import itertools
import warnings
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.axes3d import Axes3D

# local modules
import transitions

# TODO: 
# 1) add a saving-module?:
# 2) multistart-loop?
class SimulatedMinimumDistance():
    ''' 
    This class performs simulated minimum distance (self) estimation.
    Input requirements are
    - model: Class with solution and simulation capabilities: model.solve() and model.simulate(). 
             Properties of model should be contained in model.par
    - mom_data: np.array (1d) of moments in the data to be used for estimation
    - mom_fun: function used to calculate moments in simulated data. Should return a 1d np.array
    
    '''    

    def __init__(self,model,mom_data,mom_fun,recompute=False,bounds=None,name='baseline',method='nelder-mead',est_par=[],par_save={},options={'disp': False},print_iter=[False,1],save=False,**kwargs): # called when created
        
        # settings for model
        self.model = model
        self.mom_data = mom_data
        self.mom_fun = mom_fun
        self.recompute = recompute
        self.name = name

        # settings for estimation
        self.bounds = bounds
        self.options = options
        self.method = method
        self.est_par = est_par

        # settings for printing and saving
        self.save = save
        self.par_save = par_save     
        self.obj_save = []   
        self.print_iter = print_iter
        self.iter = 0
        self.time = {self.iter: time.time()}

    def obj_fun(self,theta,W,*args):
        
        # print parameters
        if self.print_iter[0]:
            self.iter += 1
            if self.iter % self.print_iter[1] == 0:
                self.time[self.iter] = time.time()
                toctic = self.time[self.iter] - self.time[self.iter-self.print_iter[1]]
                print('Iteration:', self.iter, '(' + str(np.round(toctic/60,2)) + ' minutes)')
                for p in range(len(theta)):
                    print(f' {self.est_par[p]}={theta[p]:2.4f}', end='')

        # hardcode constraint on variance
        if 'sigma_eta' in self.est_par and theta[self.est_par.index('sigma_eta')] < 0:
            self.obj = np.inf
        else:

            # 1. update parameters 
            for i in range(len(self.est_par)):
                setattr(self.model.par,self.est_par[i],theta[i]) # like par.key = val
                if self.model.couple and hasattr(self.model.Single.par,self.est_par[i]):
                    setattr(self.model.Single.par,self.est_par[i],theta[i]) # update also in nested single model                

            # update of phi0 - just uncomment this, when estimating both
            if 'phi_0_male' in self.est_par:
                idx = self.est_par.index('phi_0_male')
                setattr(self.model.par,'phi_0_female',theta[idx])

            elif 'phi_0_female' in self.est_par:
                idx = self.est_par.index('phi_0_female')
                setattr(self.model.par,'phi_0_male',theta[idx])

            # 2. solve model with current parameters
            self.model.solve(recompute=self.recompute)

            # 3. simulate data from the model and calculate moments [have this as a complete function, used for standard errors]
            self.model.simulate()
            self.mom_sim = self.mom_fun(self.model,*args)

            # 4. calculate objective function and return it
            diff = self.mom_data - self.mom_sim
            self.obj  = ((np.transpose(diff) @ W) @ diff)

        # print obj
        if self.print_iter[0]:
            if self.iter % self.print_iter[1] == 0:
                print(f' -> {self.obj:2.4f}')

        # save
        if self.save:
            for p in range(len(theta)):
                self.par_save[self.est_par[p]].append(theta[p])
            self.obj_save.append(self.obj)                
                    
        # return
        return self.obj 

    def estimate(self,theta0,W,*args):
        # TODO: consider multistart-loop with several algortihms - that could alternatively be hard-coded outside
        assert(len(W[0])==len(self.mom_data)) # check dimensions of W and mom_data

        # estimate
        self.est_out = minimize(self.obj_fun, theta0, (W, *args), bounds=self.bounds, method=self.method,options=self.options)

        # return output
        self.est = self.est_out.x
        self.W = W     
    
    def MultiStart(self,theta0,weight,options={'print': True, 'time': 'min', 'finalN': int(5e5)}):
            
        # time
        tic_total = time.time()
            
        # preallocate
        theta = np.nan*np.zeros(np.array(theta0).shape)
        obj = np.nan*np.zeros(len(theta0))

        # options
        self.options['xatol'] = 0.001
        self.options['fatol'] = 0.001        
            
        for p in range(len(theta0)):
                
            # estimate
            tic = time.time()
            self.estimate(theta0[p],weight)
            toc = time.time()
                
            # save
            theta[p] = self.est
            obj[p] = self.obj
                
            # print
            if options['print']:
                    
                if options['time'] == 'sec':
                    tid = str(np.round(toc-tic,1)) + ' sec'
                if options['time'] == 'min':
                    tid = str(np.round((toc-tic)/60,1)) + ' min'
                if options['time'] == 'hours':
                    tid = str(np.round((toc-tic)/(60**2),1)) + ' hours'
                    
                print(p+1, 'estimation:')
                print('success:', self.est_out.success,'|', 'feval:', self.est_out.nfev, '|', 
                      'time:', tid, '|', 'obj:', self.obj)
                print('start par:', theta0[p])
                print('par:      ', self.est)
                print('')
                    
        # final estimation
        # change settings
        self.options['xatol'] = 0.0001
        self.options['fatol'] = 0.0001
        startN = self.model.par.simN
        self.model.par.simN = options['finalN']
        self.model.recompute()

        # estimate
        idx = np.argmin(obj)
        self.estimate(theta[idx],weight)
        toc_total = time.time()
        
        # prints
        if options['print']:
            print('final estimation:')
            print('success:', self.est_out.success,'|', 'feval:', self.est_out.nfev, '|', 'obj:', self.obj)
            print('total estimation time:', str(np.round((toc_total-tic_total)/(60**2),1)) + ' hours')
            print('start par:', theta[idx])            
            print('par:', self.est)
            print('')

        # reset N
        self.model.par.simN = startN
        self.model.recompute()

    def std_error(self,theta,Omega,W,Nobs,Nsim,step=1.0e-4,*args):
        ''' Calculate standard errors and sensitivity measures '''

        num_par = len(theta)
        num_mom = len(W[0])
        
        # 1. numerical gradient. The objective function is (data - sim)'*W*(data - sim) so take the negative of mom_sim
        grad = np.empty((num_mom,num_par))
        for p in range(num_par):
            theta_now = theta[:] 

            step_now  = np.zeros(num_par)
            step_now[p] = np.fmax(step,step*theta_now[p])

            self.obj_fun(theta_now + step_now,W,*args)
            mom_forward = - self.mom_sim

            self.obj_fun(theta_now - step_now,W,*args)
            mom_backward = - self.mom_sim

            grad[:,p] = (mom_forward - mom_backward)/(2.0*step_now[p])

        # 2. asymptotic standard errors [using Omega: V(mom_data_i). If bootstrapped, remember to multiply by Nobs]
        GW  = np.transpose(grad) @ W
        GWG = GW @ grad

        Avar = np.linalg.inv(GWG) @ ( GW @ Omega @ np.transpose(GW) ) @ np.linalg.inv(GWG)
        fac  = (1.0 + 1.0/Nsim)/Nobs # Nsim: number of simulated observations, Nobs: number of observations in data
        self.std = np.sqrt( fac*np.diag(Avar) )

        # 3. Sensitivity measures
        self.sens1 = - np.linalg.inv(GWG) @ GW  # Andrews I, Gentzkow M, Shapiro JM: "Measuring the Sensitivity of Parameter Estimates to Estimation Moments." Quarterly Journal of Economics. 2017;132 (4) :1553-1592
       
    def sensitivity(self,theta,W,fixed_par_str=None,step=1.0e-4,*args):
        ''' sensitivity measures '''

        num_par = len(theta)
        num_mom = len(W[0])

        # 1. numerical gradient. The objective function is (data - sim)'*W*(data - sim) so take the negative of mom_sim
        grad = np.empty((num_mom,num_par))
        for p in range(num_par):
            theta_now = theta[:] 

            step_now    = np.zeros(num_par)
            step_now[p] = np.fmax(step,step*theta_now[p])

            self.obj_fun(theta_now + step_now,W,*args)
            mom_forward = - self.mom_sim

            self.obj_fun(theta_now - step_now,W,*args)
            mom_backward = - self.mom_sim

            grad[:,p] = (mom_forward - mom_backward)/(2.0*step_now[p])
        
        # 2. Sensitivity measures
        GW  = np.transpose(grad) @ W
        GWG = GW @ grad
        Lambda = - np.linalg.inv(GWG) @ GW

        # 3. Sensitivity measures
        self.sens1 = Lambda  # Andrews I, Gentzkow M, Shapiro JM: "Measuring the Sensitivity of Parameter Estimates to Estimation Moments." Quarterly Journal of Economics. 2017;132 (4) :1553-1592

        # reset parameters
        for p in range(len(self.est_par)):
            setattr(self.model.par,self.est_par[p],theta[p])

        # DO my suggestion
        if fixed_par_str:
            # mine: calculate the numerical gradient wrt parameters in fixed_par

            # change the estimation parameters to be the fixed ones
            est_par = self.est_par
            self.est_par = fixed_par_str

            # construct vector of fixed values
            gamma = np.empty(len(self.est_par))
            for p in range(len(self.est_par)):
                gamma[p] = getattr(self.model.par,self.est_par[p])

            # calculate gradient with respect to gamma
            num_gamma = len(gamma)
            grad_g = np.empty((num_mom,num_gamma))
            for p in range(num_gamma):
                gamma_now = gamma[:] 

                step_now    = np.zeros(num_gamma)
                step_now[p] = np.fmax(step,step*gamma_now[p])

                self.obj_fun(gamma_now + step_now,W,*args)
                mom_forward = - self.mom_sim

                self.obj_fun(gamma_now - step_now,W,*args)
                mom_backward = - self.mom_sim

                grad_g[:,p] = (mom_forward - mom_backward)/(2.0*step_now[p])

            # reset parameters
            for p in range(len(self.est_par)):
                setattr(self.model.par,self.est_par[p],gamma[p])
            self.est_par = est_par

            # sensitivity
            self.sens2 = Lambda @ grad_g
            ela = np.empty((len(theta),len(gamma)))
            semi_ela = np.empty((len(theta),len(gamma)))
            for t in range(len(theta)):
                for g in range(len(gamma)):
                    ela[t,g] = self.sens2[t,g]*gamma[g]/theta[t]    
                    semi_ela[t,g] = self.sens2[t,g]/theta[t]

            self.sens2e = ela
            self.sens2semi = semi_ela

def MomFunSingle(model,calc='mean'):
    """ compute moments for single model """

    # unpack
    sim = model.sim
    states = np.unique(sim.states,axis=0)
    MA = sim.states[:,0]
    ST = sim.states[:,1]    
    probs = sim.probs[:,1:] # 1: means exclude age 57 (since first prob is at 58)
        
    # initialize
    T = probs.shape[1]
    N = len(states)
    mom = np.zeros((T,N))
    
    # compute moments
    for i in range(N):
        ma = states[i,0]
        st = states[i,1]
        idx = np.nonzero((MA==ma) & (ST==st))[0]
        with warnings.catch_warnings(): # ignore this specific warning
            warnings.simplefilter("ignore", category=RuntimeWarning)                
            if calc == 'mean': 
                mom[:,i] = np.nanmean(probs[idx,:],axis=0)
            elif calc == 'std':
                mom[:,i] = np.nanstd(probs[idx,:],axis=0)
    return mom.ravel() # collapse across rows (C-order)

def MomFunCouple_agg(model,bootstrap=False,B=1000):

    # unpack
    sim = model.sim
    par = model.par

    # 1. index
    idx_all = np.arange(len(sim.d))
    idx = np.nonzero(np.any(sim.d[:,:,0]==0,axis=1) & (np.any(sim.d[:,:,1]==0,axis=1)))[0]

    if bootstrap:
        
        # sample with replacement (B replications)
        idx_all = np.random.choice(idx_all,size=(len(idx_all),B))
        idx = np.random.choice(idx,size=(len(idx),B))                                

        # compute moments
        mom = []
        for b in range(B):
            mom.append(Couple_mom_agg(sim,par,idx_all[b],idx[b]))
        return np.array(mom)

    else:
        return Couple_mom_agg(sim,par,idx_all,idx)


def Couple_mom_agg(sim,par,idx_all,idx,ages=[58,68]):

    # unpack states
    AD = sim.states[:,0]
    ADx = np.arange(-7,8)

    # extract probs
    x = np.arange(ages[0], ages[1]+1)    
    probs_h = sim.probs[:,transitions.inv_age(x,par)+par.ad_min,1]
    probs_w = sim.probs[:,transitions.inv_age(x,par)+par.ad_min,0]             
        
    # initialize
    mom_marg = np.zeros((2,len(x))) # gender, ages/years
    mom_joint = np.zeros(15)         # retirement age diff

    # 1. marginal moments
    mom_marg[0] = np.nanmean(probs_h[idx_all],axis=0)
    mom_marg[1] = np.nanmean(probs_w[idx_all],axis=0)    

    # 2. joint moments
    ret_w = np.nanargmin(sim.d[idx,:,0],axis=1)
    ret_h = np.nanargmin(sim.d[idx,:,1],axis=1) 
    diff = (ret_h-ret_w+AD[idx])  # add age difference to put them on the same time scale    
    for j in range(len(ADx)):
        ad = ADx[j]
        mom_joint[j] = np.sum(diff==ad)
    mom_joint = mom_joint/np.sum(mom_joint)

    # return 
    return np.concatenate((mom_marg.ravel(),mom_joint)) # flatten and join them 


def MomFunCouple(model,bootstrap=False,B=1000):

    # unpack
    sim = model.sim
    par = model.par

    # unpack states
    ST_h = sim.states[:,1]
    ST_w = sim.states[:,2]

    # 1. index
    Nhs_m = np.nonzero(np.isin(ST_h,[0,2]))[0]
    hs_m = np.nonzero(np.isin(ST_h,[1,3]))[0]
    Nhs_w = np.nonzero(np.isin(ST_w,[0,2]))[0]
    hs_w = np.nonzero(np.isin(ST_w,[1,3]))[0]
    Nelig_m = np.nonzero(np.isin(ST_h,[0,1]))[0]
    elig_m = np.nonzero(np.isin(ST_h,[2,3]))[0]
    Nelig_w = np.nonzero(np.isin(ST_w,[0,1]))[0]
    elig_w = np.nonzero(np.isin(ST_w,[2,3]))[0]
    idx = np.nonzero(np.any(sim.d[:,:,0]==0,axis=1) & (np.any(sim.d[:,:,1]==0,axis=1)))[0]

    if bootstrap:
        
        # sample with replacement (B replications)
        Nhs_m = np.random.choice(Nhs_m,size=(len(Nhs_m),B))
        hs_m = np.random.choice(hs_m,size=(len(hs_m),B))
        Nhs_w = np.random.choice(Nhs_w,size=(len(Nhs_w),B))
        hs_w = np.random.choice(hs_w,size=(len(hs_w),B))
        Nelig_m = np.random.choice(Nelig_m,size=(len(Nelig_m),B))
        elig_m = np.random.choice(elig_m,size=(len(elig_m),B))
        Nelig_w = np.random.choice(Nelig_w,size=(len(Nelig_w),B))
        elig_w = np.random.choice(elig_w,size=(len(elig_w),B))        
        idx = np.random.choice(idx,size=(len(idx),B))                                

        # compute moments
        mom = []
        for b in range(B):
            mom.append(Couple_mom(sim,par,Nhs_m[b],hs_m[b],Nhs_w[b],hs_w[b],
                                          Nelig_m[b],elig_m[b],Nelig_w[b],elig_w[b],
                                          idx[b]))
        return np.array(mom)

    else:
        return Couple_mom(sim,par,Nhs_m,hs_m,Nhs_w,hs_w,
                                  Nelig_m,elig_m,Nelig_w,elig_w,
                                  idx)


def Couple_mom(sim,par,Nhs_m,hs_m,Nhs_w,hs_w,
                       Nelig_m,elig_m,Nelig_w,elig_w,
                       idx,ages=[58,68]):

    # unpack states
    AD = sim.states[:,0]
    ADx = [-4,-3,-2,-1,0,1,2,3,4]

    # extract probs
    x = np.arange(ages[0], ages[1]+1)    
    probs_h = sim.probs[:,transitions.inv_age(x,par)+par.ad_min,1]
    probs_w = sim.probs[:,transitions.inv_age(x,par)+par.ad_min,0]             
        
    # initialize
    mom_marg = np.zeros((2,4,len(x)))   # gender, education status, ages/years
    mom_joint = np.zeros(9)         # education status, retirement age diff

    # 1. marginal moments
    mom_marg[0,0] = np.nanmean(probs_h[Nhs_m],axis=0)
    mom_marg[0,1] = np.nanmean(probs_h[hs_m],axis=0)    
    mom_marg[1,0] = np.nanmean(probs_w[Nhs_w],axis=0)
    mom_marg[1,1] = np.nanmean(probs_w[hs_w],axis=0)     
    
    mom_marg[0,2] = np.nanmean(probs_h[Nelig_m],axis=0)
    mom_marg[0,3] = np.nanmean(probs_h[elig_m],axis=0)    
    mom_marg[1,2] = np.nanmean(probs_w[Nelig_w],axis=0)
    mom_marg[1,3] = np.nanmean(probs_w[elig_w],axis=0)            

    # 2. joint moments
    ret_w = np.nanargmin(sim.d[idx,:,0],axis=1)
    ret_h = np.nanargmin(sim.d[idx,:,1],axis=1)    
    diff = ret_h-ret_w+AD[idx]  # add age difference to put them on the same time scale
    for j in range(len(ADx)):
        ad = ADx[j]
        mom_joint[j] = np.sum(diff==ad)
    mom_joint = mom_joint/np.sum(mom_joint)

    # return 
    return np.concatenate((mom_marg.ravel(),mom_joint)) # flatten and join them 

def start(N,bounds):
    ''' uniformly sample starting values '''
    outer = []
    for _ in range(N):
        inner = []
        for j in range(len(bounds)):
            inner.append(np.round(np.random.uniform(bounds[j][0],bounds[j][1]),3))
        outer.append(inner)
    return outer    

def identification(model,true_par,est_par,true_save,par_save,par_latex,start,end,N,plot=True,save_plot=True):
    ''' plot of objective as a function of par_save '''

    # update parameters
    for i in range(len(est_par)):
        setattr(model.par, est_par[i], true_par[i])
        if model.couple and hasattr(model.Single.par,est_par[i]):
            setattr(model.Single.par,est_par[i],true_par[i])            
    
    # data
    model.solve()
    model.simulate()
    def mom_fun(model):
        return MomFunCouple(model)    
    mom_data = mom_fun(model)
    weight = np.eye(mom_data.size)
    
    # grids
    x1 = np.linspace(start[0],end[0],N)
    x2 = np.linspace(start[0],end[0],N)
    x1,x2 = np.meshgrid(x1,x2)
    x1,x2 = x1.ravel(),x2.ravel()
    
    # estimate
    smd = SimulatedMinimumDistance(model,mom_data,mom_fun,save=True)
    smd.est_par = par_save
    smd.par_save = {par_save[0]: [], par_save[1]: []}
    for i in range(N*N):
        print(i, end=' ')    # track progress because it takes so long time
        theta = [x1[i],x2[i]]
        smd.obj_fun(theta,weight)
    
    # reset parameters
    for i in range(len(est_par)):
        setattr(model.par, est_par[i], true_par[i])
        if model.couple and hasattr(model.Single.par,est_par[i]):
            setattr(model.Single.par,est_par[i],true_par[i])                
    
    # return
    x1 = x1.reshape(N,N) 
    x2 = x2.reshape(N,N)
    y = np.array(smd.obj_save).reshape(N,N)
    if plot:
        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')
        ax.plot_surface(x1,x2,y, 
                        rstride=2, cstride=2,
                        cmap=plt.cm.jet,
                        alpha=0.7,
                        linewidth=0.25)
        ax.xaxis.set_rotate_label(False)
        ax.yaxis.set_rotate_label(False)
        ax.set_xlabel(par_latex[0], fontsize=20)
        ax.set_ylabel(par_latex[1], fontsize=20)
        ax.set_xticklabels(['',np.round(np.min(x1),1),'','','','',np.round(np.max(x1),1)])
        ax.set_yticklabels(['',np.round(np.min(x2),1),'','','','',np.round(np.max(x2),1)])
        ax.tick_params(axis='both', which='major', labelsize=12)  
        fig.tight_layout()
        if save_plot:
            return fig        
    else:
        return x1,x2,y

def save_est(est_par,theta,name):
    """ save estimated parameters to "estimates"-folder """
    EstDict = dict(zip(est_par,theta))
    with open('estimates/'+str(name)+'.pickle', 'wb') as handle:
        pickle.dump(EstDict, handle, protocol=pickle.HIGHEST_PROTOCOL)

def load_est(name,couple=False):
    """ load estimated parameters from "estimates"-folder """    
    with open('estimates/'+str(name)+'.pickle', 'rb') as handle:
        EstDict = pickle.load(handle)
    
    if couple:
        single_par = ['alpha_0_male', 'alpha_0_female', 'alpha_1', 'sigma_eta']
        CoupleDict = {}
        SingleDict = {}
        for key,val in EstDict.items():
            CoupleDict[key] = val
            if key in single_par:
                SingleDict[key] = val
        return CoupleDict,SingleDict
    else:
        return EstDict
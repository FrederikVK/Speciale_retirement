# -*- coding: utf-8 -*-
"""RetirementModel

Solves the retirement model from the "Dynamic Programming" course.

"""

##############
# 1. imports #
##############

import yaml
yaml.warnings({'YAMLLoadWarning': False})

import time
import numpy as np
from numba import boolean, int32, double
import itertools

# consav package
from consav import linear_interp # for linear interpolation
from consav import misc # various tools
from consav import ModelClass # baseline model class

# local modules
import utility
import last_period
import post_decision
import egm
import simulate
import figs
import funs
import transitions

############
# 2. model #
############

class RetirementModelClass(ModelClass):
    
    #########
    # setup #
    #########
    
    def __init__(self,name='baseline',load=False,solmethod='egm',compiler='vs',**kwargs):
        """ basic setup

        Args:

            name (str,optional): name, used when saving/loading
            load (bool,optinal): load from disc
            solmethod (str,optional): solmethod, used when solving
            compiler (str,optional): compiler, 'vs' or 'intel' (used for C++)
             **kwargs: change to baseline parameter in .par
            
        Define parlist, sollist and simlist contain information on the
        model parameters and the variables when solving and simulating.

        Call .setup(**kwargs).

        """        

        self.name = name 
        self.solmethod = solmethod
        self.compiler = compiler
        self.vs_path = 'C:/Program Files (x86)/Microsoft Visual Studio/2017/Community/VC/Auxiliary/Build/'
        self.intel_path = 'C:/Program Files (x86)/IntelSWTools/compilers_and_libraries_2018.5.274/windows/bin/'
        self.intel_vs_version = 'vs2017'
        
        # a. define subclasses
        parlist = [ # (name,numba type), parameters, grids etc.
            
            # time parameters
            ('T',int32),
            ('Tr',int32), # forced retirement
            
            # preference parameters
            ('rho',double), 
            ('beta',double),
            ('alpha_0_male',double), # leisure
            ('alpha_0_female',double),
            ('alpha_1',double),
            ('alpha_2',double),
            ('gamma',double), # bequest motive

            # uncertainty/variance parameters
            ('sigma_eta',double), # taste shock
            ('sigma_xi_men',double), # income shock
            ('sigma_xi_women',double), # income shock            

            # savings
            ('R',double), # interest rate
            
            # grids            
            ('grid_a',double[:]),
            ('a_work',double[:,:]), # broadcasting grid_a into matrix     
            ('a_max',int32), # a_grid
            ('a_phi',int32),
            ('Na',int32),
            ('poc',int32), 
            ('Nxi',int32), # GH-points
            
            # states
            ('states',double[:]),

            # tax system
            ('tau_upper',double),
            ('tau_LMC',double),
            ('WD',double),
            ('WD_upper',double),
            ('tau_c',double),
            ('y_low',double),
            ('y_low_m',double),
            ('y_low_u',double),
            ('tau_h',double),
            ('tau_l',double),
            ('tau_m',double),
            ('tau_u',double),
            ('tau_max',double),                                                                                                

            # misc
            ('tol',double),
            ('do_print',boolean),
            ('do_simple_w',boolean),
            ('cppthreads',int32),
            
            # simulation
            ('simT',int32), 
            ('simN',int32), 
            ('sim_seed',int32)
        ]
        
        sollist = [ # (name, numba type), solution data

            # solution
            ('c',double[:,:,:,:,:]),
            ('m',double[:,:,:,:,:]),
            ('v',double[:,:,:,:,:]),            

            # interpolation
            ('c_plus_interp',double[:,:,:,:,:]),
            ('v_plus_interp',double[:,:,:,:,:]),           
            
            # post decision
            ('q',double[:,:,:,:,:]),                    
            ('v_plus_raw',double[:,:,:,:,:])                       
        ]        

        simlist = [ # (name, numba type), simulation data       

            # solution
            ('c',double[:,:]),            
            ('m',double[:,:]),
            ('v',double[:,:]),                      
            ('a',double[:,:]),
            ('d',double[:,:]), # retirement choice

            # dummies and probabilities
            ('alive',double[:,:]), # dummy for alive
            ('probs',double[:,:]), # retirement probs
            ('ret_age',double[:]), # retirement age

            # interpolation   
            ('c_interp',double[:,:,:]),
            ('v_interp',double[:,:,:]),                        

            # random shocks
            ('unif',double[:,:]),
            ('deadP',double[:,:]),
            ('inc_shock',double[:,:]),

            # states
            ('states',double[:])
        ]      

        # b. create subclasses
        self.par,self.sol,self.sim = self.create_subclasses(parlist,sollist,simlist)

        # note: the above returned classes are in a format where they can be used in numba functions

        # c. load
        if load:
            self.load()
        else:
            self.setup(**kwargs)

    def setup(self,**kwargs):
        """ define baseline values and update with user choices

        Args:

             **kwargs: change to baseline parameters in .par

        """              
        # time parameters
        self.par.T = 110-57+1 # 57 to 110 years
        self.par.Tr = 77-57+1 # forced retirement at 77 years        
        
        # preference parameters
        self.par.rho = 0.96
        self.par.beta = 0.98        
        self.par.alpha_0_male = 0.160 # constant
        self.par.alpha_0_female = 0.119 + 0.05 # constant
        self.par.alpha_1 = 0.053 # high skilled
        self.par.alpha_2 = -0.036 # children
        self.par.gamma = 0.08 # bequest motive

        # uncertainty/variance parameters
        self.par.sigma_eta = 0.435 # taste shock
        self.par.sigma_xi_men = np.sqrt(0.544) # income shock
        self.par.sigma_xi_women = np.sqrt(0.399) # income shock        

        # savings
        self.par.R = 1.03 # interest rate

        # grids
        self.par.a_max = 100 # 10 mio. kr. denominated in 100.000 kr
        self.par.a_phi = 1.1
        self.par.Na = 150
        self.par.poc = 10 # points on constraint
        self.par.Nxi = 8          

        # states
        self.par.states = list(itertools.product([0, 1], repeat=4))
        self.par.var = {'male': 0, 'elig': 1, 'high_skilled': 2, 'children': 3}

        # tax system
        self.par.tau_upper = 0.59
        self.par.tau_LMC = 0.08
        self.par.WD = 0.4
        self.par.WD_upper = 12300/100000
        self.par.tau_c = 0.2554
        self.par.y_low = 41000/100000
        self.par.y_low_m = 279800/100000
        self.par.y_low_u = 335800/100000
        self.par.tau_h = 0.08
        self.par.tau_l = 0.0548
        self.par.tau_m = 0.06
        self.par.tau_u = 0.15
        self.par.tau_max = self.par.tau_l + self.par.tau_m + self.par.tau_u + self.par.tau_c + self.par.tau_h - self.par.tau_upper
        
        # misc
        self.par.tol = 1e-8
        self.par.do_print = True
        self.par.do_simple_w = False
        self.par.cppthreads = 1

        # simulation
        self.par.simT = self.par.T
        self.par.simN = 1000
        self.par.sim_seed = 1998
        self.par.simM_init = 5*np.ones(self.par.simN)
        self.par.simStates = np.zeros(self.par.simN,dtype=int)

        # b. update baseline parameters using keywords 
        for key,val in kwargs.items():
            setattr(self.par,key,val) # like par.key = val
        
        # c. setup_grids
        self.setup_grids()
        
    def setup_grids(self):
        """ construct grids for states and shocks """

        # a. post-decision states (unequally spaced vector of length Na)
        self.par.grid_a = misc.nonlinspace(1e-6,self.par.a_max,self.par.Na,self.par.a_phi)
        
        # b. shocks (qudrature nodes and weights using GaussHermite)
        self.par.xi_men,self.par.xi_men_w = funs.GaussHermite_lognorm(self.par.sigma_xi_men,self.par.Nxi)
        self.par.xi_women,self.par.xi_women_w = funs.GaussHermite_lognorm(self.par.sigma_xi_women,self.par.Nxi)        

        # c. create tiled/broadcasted arrays to use in compute
        #self.par.a_work = np.transpose(np.array([self.par.grid_a]*self.par.Nxi))
        #self.par.xi_men_work = np.array([self.par.xi_men]*self.par.Na)
        #self.par.xi_women_work = np.array([self.par.xi_women]*self.par.Na)        

        # d. set seed
        np.random.seed(self.par.sim_seed)

    #########
    # solve #
    #########

    def _solve_prep(self):
        """ allocate memory for solution """

        # prep
        par = self.par
        num_st = len(par.states) # number of states

        # solution
        self.sol.c = np.nan*np.ones((par.T,num_st,par.Na+par.poc,2,3)) # 3 in the end is for storing ad hoc/extra solutions, when recalculating erp   
        self.sol.m = np.nan*np.zeros((par.T,num_st,par.Na+par.poc,2,3))
        self.sol.v = np.nan*np.zeros((par.T,num_st,par.Na+par.poc,2,3))              

        # interpolation
        self.sol.c_plus_interp = np.nan*np.zeros((par.T-1,num_st,par.Na,2,3))
        self.sol.v_plus_interp = np.nan*np.zeros((par.T-1,num_st,par.Na,2,3)) 

        # post decision        
        self.sol.q = np.nan*np.zeros((par.T-1,num_st,par.Na,2,3))
        self.sol.v_plus_raw = np.nan*np.zeros((par.T-1,num_st,par.Na,2,3))

    def solve(self):
        """ solve the model """

        # prep
        par = self.par
        sol = self.sol

        # a. allocate solution
        self._solve_prep()
        
        # b. backwards induction
        for t in reversed(range(par.T)):       
            for st in range(len(par.states)): # loop over states
            
                # i. last period
                if t == par.T-1:
                
                    last_period.solve(t,st,sol,par)

                # ii. if forced to retire (retirement decision is made one period ahead)
                elif t+1 >= par.Tr-1:

                    post_decision.compute_retired(t,st,sol,par,[0,0,0]) # take t+1 sol from main sol, assume erp with two year rule (doesn't matter), store t sol in main sol
                    egm.solve_bellman_retired(t,st,sol,par,[0,0,0])
                
                # iii. oap period (retirement decision is made on period ahead)
                elif transitions.age(t+1) >= 65: 
                    egm.post_and_egm(t,st,sol,par,[0,0,0]) # just a wrapper, which runs both post decision and egm functions

                # iv. erp period - here we have to recalculate solutions if eligible to erp
                elif (59 <= transitions.age(t+1) <= 64 and transitions.state_translate(st,'elig',par) == 1):
                    egm.recalculate(t,st,sol,par)

                # v. before erp periods
                else:
                    egm.post_and_egm(t,st,sol,par,[0,2,0]) # take t+1 sol from main sol, assume no erp, store t sol in main sol                    


    ############
    # simulate #
    ############

    def _simulate_prep(self):
        """ allocate memory for simulation and draw random numbers """

        # prep
        par = self.par
        sim = self.sim

        # solution
        sim.c = np.nan*np.zeros((par.simT,par.simN))
        sim.m = np.nan*np.zeros((par.simT,par.simN))
        sim.a = np.nan*np.zeros((par.simT,par.simN))
        sim.d = np.nan*np.zeros((par.simT,par.simN)) # retirement choice

        # dummies and probabilities
        sim.alive = np.ones((par.simT,par.simN)) #dummy for alive
        sim.probs = np.zeros((par.simT,par.simN)) # retirement probs
        sim.ret_age = np.nan*np.zeros(par.simN) # retirement age

        # interpolation
        sim.c_interp = np.nan*np.zeros((par.simT,par.simN,2))
        sim.v_interp = np.nan*np.zeros((par.simT,par.simN,2))    

        # b. initialize m and d
        sim.m[0,:] = par.simM_init        
        sim.d[0,:] = np.ones(par.simN) # all is working at t=0

        # c. states
        sim.states = par.simStates

        # d. draw random shocks
        sim.unif = np.random.rand(par.simT,par.simN) # taste shocks
        sim.deadP = np.random.rand(par.simT,par.simN) # death probs
        sim.inc_shock = np.nan*np.zeros((par.Tr-1,par.simN)) # income shocks
        for i in range(len(sim.states)): 
            if transitions.state_translate(sim.states[i],'male',par) == 1:
                sim.inc_shock[:,i] = np.random.lognormal(-0.5*(par.sigma_xi_men**2),par.sigma_xi_men,size=par.Tr-1)
            else:
                sim.inc_shock[:,i] = np.random.lognormal(-0.5*(par.sigma_xi_women**2),par.sigma_xi_women,size=par.Tr-1)


    def simulate(self):
        """ simulate model """

        # a. allocate memory and draw random numbers
        self._simulate_prep()

        # b. simulate
        self.par.simT = self.par.T
        simulate.lifecycle(self.sim,self.sol,self.par)


    def test(self):
        """ method for specifying test """
        
        # a. save print status
        do_print = self.par.do_print
        self.par.do_print = False

        # b. test run
        self.solve()

        # c. timed run
        tic = time.time()  
        self.solve()
        toc = time.time()
        print(f'solution time: {toc-tic:.1f} secs')

        # d. reset print status
        self.par.do_print = do_print        


#to debug code
from consav import runtools
runtools.write_numba_config(disable=1,threads=8)
model = RetirementModelClass(name='baseline',solmethod='egm')
model.solve()
model.simulate()

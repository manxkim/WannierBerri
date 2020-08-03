#                                                            #
# This file is distributed as part of the WannierBerri code  #
# under the terms of the GNU General Public License. See the #
# file `LICENSE' in the root directory of the WannierBerri   #
# distribution, or http://www.gnu.org/copyleft/gpl.txt       #
#                                                            #
# The WannierBerri code is hosted on GitHub:                 #
# https://github.com/stepan-tsirkin/wannier-berri            #
#                     written by                             #
#           Stepan Tsirkin, University of Zurich             #
#   some parts of this file are originate                    #
# from the translation of Wannier90 code                     #
#------------------------------------------------------------#

import numpy as np
from scipy.io import FortranFile 
import copy
import lazy_property
import functools
import multiprocessing 
#import billiard as multiprocessing 
from .__utility import str2bool, alpha_A, beta_A, iterate3dpm, real_recip_lattice,fourier_q_to_R
from colorama import init
from termcolor import cprint 
from .__system import System, ws_dist_map
from .__w90_files import EIG,MMN,CheckPoint,SPN,UHU,SIU,SHU
from time import time

class System_w90(System):

    def __init__(self,seedname="wannier90",
                    berry=False,spin=False,morb=False,SHC=False,
                    use_ws=True,
                    transl_inv=True,
                    frozen_max=-np.Inf,
                    random_gauge=False,
                    degen_thresh=-1 ,
                    fft='fftw',
                    npar=multiprocessing.cpu_count()  ):

        self.seedname=seedname

        self.morb  = morb
        self.berry = berry
        self.spin  = spin
        self.SHC   = SHC

        self.AA_R=None
        self.BB_R=None
        self.CC_R=None
        self.FF_R=None
        self.SS_R=None
        self.SA_R=None
        self.SHA_R=None


        getAA = False
        getBB = False
        getCC = False
        getSS = False
        getFF = False
        getSA = False
        getSHA = False
    
        if self.morb: 
            getAA=getBB=getCC=True
        if self.berry: 
            getAA=True
        if self.spin: 
            getSS=True
        if self.SHC:
            getAA=getSS=getSA=getSHA=True

        self.frozen_max=frozen_max
        self.random_gauge=random_gauge
        self.degen_thresh=degen_thresh

        chk=CheckPoint(self.seedname)
        self.real_lattice,self.recip_lattice=real_recip_lattice(chk.real_lattice,chk.recip_lattice)
        self.iRvec,self.Ndegen=self.wigner_seitz(chk.mp_grid)
#        print ("number of R-vectors: {} ; vectrors:\n {}".format(self.iRvec.shape[0], self.iRvec,self.Ndegen))
        self.nRvec0=len(self.iRvec)
        self.num_wann=chk.num_wann

        eig=EIG(seedname)
        if getAA or getBB:
            mmn=MMN(seedname)

        kpt_mp_grid=[tuple(k) for k in np.array( np.round(chk.kpt_latt*np.array(chk.mp_grid)[None,:]),dtype=int)%chk.mp_grid]
#        print ("kpoints:",kpt_mp_grid)

        fourier_q_to_R_loc=functools.partial(fourier_q_to_R, mp_grid=chk.mp_grid,kpt_mp_grid=kpt_mp_grid,iRvec=self.iRvec,ndegen=self.Ndegen,numthreads=npar,fft=fft)

        timeFFT=0
        HHq=chk.get_HH_q(eig)
        t0=time()
        self.HH_R=fourier_q_to_R_loc( HHq )
        timeFFT+=time()-t0
#        for i in range(self.nRvec):
#            print (i,self.iRvec[i],"H(R)=",self.HH_R[0,0,i])

        if getAA:
            AAq=chk.get_AA_q(mmn,transl_inv=transl_inv)
            t0=time()
            self.AA_R=fourier_q_to_R_loc(AAq)
            timeFFT+=time()-t0

        if getBB:
            t0=time()
            self.BB_R=fourier_q_to_R_loc(chk.get_AA_q(mmn,eig))
            timeFFT+=time()-t0

        if getCC:
            uhu=UHU(seedname)
            t0=time()
            self.CC_R=fourier_q_to_R_loc(chk.get_CC_q(uhu,mmn))
            timeFFT+=time()-t0
            del uhu

        if getSS:
            spn=SPN(seedname)
            t0=time()
            self.SS_R=fourier_q_to_R_loc(chk.get_SS_q(spn))
            timeFFT+=time()-t0
            del spn
        if getSA:
            siu=SIU(seedname)
            t0=time()
            self.SA_R=fourier_q_to_R_loc(chk.get_SA_q(siu,mmn))
            timeFFT+=time()-t0
            del siu
        if getSHA:
            shu=SHU(seedname)
            t0=time()
            self.SHA_R=fourier_q_to_R_loc(chk.get_SHA_q(shu,mmn))
            timeFFT+=time()-t0
            del shu

        print ("time for FFT_q_to_R : {} s".format(timeFFT))

        if  use_ws:
            print ("using ws_distance")
            ws_map=ws_dist_map_gen(self.iRvec,chk.wannier_centres, chk.mp_grid,self.real_lattice)
            for X in ['HH','AA','BB','CC','SS','FF','SA','SHA']:
                XR=X+'_R'
                if vars(self)[XR] is not None:
                    print ("using ws_dist for {}".format(XR))
                    vars(self)[XR]=ws_map(vars(self)[XR])
            self.iRvec=np.array(ws_map._iRvec_ordered,dtype=int)

        print ("Number of wannier functions:",self.num_wann)
        print ("Number of R points:", self.nRvec)
        print ("Minimal Number of K points:", self.NKFFTmin)
        print ("Real-space lattice:\n",self.real_lattice)

    def wigner_seitz(self,mp_grid):
        real_metric=self.real_lattice.T.dot(self.real_lattice)
        mp_grid=np.array(mp_grid)
        irvec=[]
        ndegen=[]
        for n in iterate3dpm(mp_grid):
            # Loop over the 125 points R. R=0 corresponds to i1=i2=i3=0,
            # or icnt=63  (62 starting from zero)
            dist=[]
            for i in iterate3dpm((2,2,2)):
                ndiff=n-i*mp_grid
                dist.append(ndiff.dot(real_metric.dot(ndiff)))
            dist_min = np.min(dist)
            if  abs(dist[62] - dist_min) < 1.e-7 :
                irvec.append(n)
                ndegen.append(np.sum( abs(dist - dist_min) < 1.e-7 ))
    
        return np.array(irvec),np.array(ndegen)


class ws_dist_map_gen(ws_dist_map):

    def __init__(self,iRvec,wannier_centres, mp_grid,real_lattice):
    ## Find the supercell translation (i.e. the translation by a integer number of
    ## supercell vectors, the supercell being defined by the mp_grid) that
    ## minimizes the distance between two given Wannier functions, i and j,
    ## the first in unit cell 0, the other in unit cell R.
    ## I.e., we find the translation to put WF j in the Wigner-Seitz of WF i.
    ## We also look for the number of equivalent translation, that happen when w_j,R
    ## is on the edge of the WS of w_i,0. The results are stored 
    ## a dictionary shifts_iR[(iR,i,j)]
        ws_search_size=np.array([2]*3)
        ws_distance_tol=1e-5
        cRvec=iRvec.dot(real_lattice)
        mp_grid=np.array(mp_grid)
        shifts_int_all= np.array([ijk  for ijk in iterate3dpm(ws_search_size+1)])*np.array(mp_grid[None,:])
        self.num_wann=wannier_centres.shape[0]
        self._iRvec_new=dict()

        for ir,iR in enumerate(iRvec):
          for jw in range(self.num_wann):
            for iw in range(self.num_wann):
              # function JW translated in the Wigner-Seitz around function IW
              # and also find its degeneracy, and the integer shifts needed
              # to identify it
              R_in=-wannier_centres[iw] +cRvec[ir] + wannier_centres[ jw]
              dist=np.linalg.norm( R_in[None,:]+shifts_int_all.dot(real_lattice),axis=1)
              irvec_new=iR+shifts_int_all[ dist-dist.min() < ws_distance_tol ].copy()
              self._add_star(ir,irvec_new,iw,jw)
        self._init_end(iRvec.shape[0])




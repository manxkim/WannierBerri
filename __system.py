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
#                                                            #
#------------------------------------------------------------

import numpy as np
from scipy.io import FortranFile as FF
import copy
import lazy_property

from .__utility import str2bool, alpha_A, beta_A , real_recip_lattice
from  .__symmetry import Group
from colorama import init
from termcolor import cprint 



class System():

    def __init__(self,seedname="wannier90",tb_file=None,
                    getAA=False,
                    getBB=False,getCC=False,
                    getSS=False,
                    getFF=False,
                    getSA=False,
                    getSHA=False,
                    use_ws=True,
                    frozen_max=-np.Inf,
                    random_gauge=False,
                    degen_thresh=-1 ,
                    old_format=False
                                ):


        if tb_file is not None:
            raise ValueError("to start from a _tb.dat file now use the System_tb() class")

        self.frozen_max=frozen_max
        self.random_gauge=random_gauge
        self.degen_thresh=degen_thresh
        self.old_format=old_format
        self.AA_R=None
        self.BB_R=None
        self.CC_R=None
        self.FF_R=None
        self.SS_R=None
        self.SA_R=None
        self.SHA_R=None



        cprint ("Reading from {}".format(seedname+"_HH_save.info"),'green', attrs=['bold'])

        f=open(seedname+"_HH_save.info" if self.old_format else seedname+"_R.info","r")
        l=f.readline().split()[:3]
        self.seedname=seedname
        self.num_wann,nRvec=int(l[0]),int(l[1])
        self.nRvec0=nRvec
        real_lattice=np.array([f.readline().split()[:3] for i in range(3)],dtype=float)
        self.real_lattice,self.recip_lattice=real_recip_lattice(real_lattice=real_lattice)
        iRvec=np.array([f.readline().split()[:4] for i in range(nRvec)],dtype=int)
        
        self.Ndegen=iRvec[:,3]
        self.iRvec=iRvec[:,:3]

        self.cRvec=self.iRvec.dot(self.real_lattice)


        print ("Number of wannier functions:",self.num_wann)
        print ("Number of R points:", self.nRvec)
        print ("Minimal Number of K points:", self.NKFFTmin)
        print ("Real-space lattice:\n",self.real_lattice)
        #print ("R - points and dege=neracies:\n",iRvec)
        has_ws=str2bool(f.readline().split("=")[1].strip())

        
        if has_ws and use_ws:
            print ("using ws_dist")
            self.ws_map=ws_dist_map_read(self.iRvec,self.num_wann,f.readlines())
            self.iRvec=np.array(self.ws_map._iRvec_ordered,dtype=int)
        else:
            self.ws_map=None
        
        f.close()
        if getCC:
           getBB=True

        self.HH_R=self.__getMat('HH')


        
        if getAA:
            self.AA_R=self.__getMat('AA')

        if getBB:
            self.BB_R=self.__getMat('BB')
        
        if getCC:
            try:
                self.CC_R=1j*self.__getMat('CCab')
            except:
                _CC_R=self.__getMat('CC')
                self.CC_R=1j*(_CC_R[:,:,:,alpha_A,beta_A]-_CC_R[:,:,:,beta_A,alpha_A])

        if getFF:
            try:
                self.FF_R=1j*self.__getMat('FFab')
            except:
                _FF_R=self.__getMat('FF')
                self.FF_R=1j*(_FF_R[:,:,:,alpha_A,beta_A]-_FF_R[:,:,:,beta_A,alpha_A])

        if getSS:
            self.SS_R=self.__getMat('SS')

        if getSA:
            self.SA_R=self.__getMat('SA')
        if getSHA:
            self.SHA_R=self.__getMat('SHA')

        cprint ("Reading the system finished successfully",'green', attrs=['bold'])


    def to_tb_file(self,tb_file=None):
        if tb_file is None: 
            tb_file=self.seedname+"_fromchk_tb.dat"
        f=open(tb_file,"w")
        f.write("written by wannier-berri form the chk file\n")
#        cprint ("reading TB file {0} ( {1} )".format(tb_file,l.strip()),'green', attrs=['bold'])
        np.savetxt(f,self.real_lattice)
        f.write("{}\n".format(self.num_wann))
        f.write("{}\n".format(self.nRvec))
        for i in range(0,self.nRvec,15):
            a=self.Ndegen[i:min(i+15,self.nRvec)]
            f.write("  ".join("{:2d}".format(x) for x in a)+"\n")
        for iR in range(self.nRvec):
            f.write("\n  {0:3d}  {1:3d}  {2:3d}\n".format(*tuple(self.iRvec[iR])))
            f.write("".join("{0:3d} {1:3d} {2:15.8e} {3:15.8e}\n".format(
                         m+1,n+1,self.HH_R[m,n,iR].real*self.Ndegen[iR],self.HH_R[m,n,iR].imag*self.Ndegen[iR]) 
                             for n in range(self.num_wann) for m in range(self.num_wann)) )
        if hasattr(self,'AA_R'):
          for iR in range(self.nRvec):
            f.write("\n  {0:3d}  {1:3d}  {2:3d}\n".format(*tuple(self.iRvec[iR])))
            f.write("".join("{0:3d} {1:3d} ".format(
                         m+1,n+1) + " ".join("{:15.8e} {:15.8e}".format(a.real,a.imag) for a in self.AA_R[m,n,iR]*self.Ndegen[iR] )+"\n"
                             for n in range(self.num_wann) for m in range(self.num_wann)) )
        f.close()
        

    def _FFT_compatible(self,FFT,iRvec):
        "check if FFT is enough to fit all R-vectors"
        return np.unique(iRvec%FFT,axis=0).shape[0]==iRvec.shape[0]


#    @lazy_property.LazyProperty
    @property
    def NKFFTmin(self):
        "finds a minimal FFT grid on which different R-vectors do not overlap"
        NKFFTmin=np.ones(3,dtype=int)
        for i in range(3):
            R=self.iRvec[:,i]
            if len(R[R>0])>0: 
                NKFFTmin[i]+=R.max()
            if len(R[R<0])>0: 
                NKFFTmin[i]-=R.min()
        assert self._FFT_compatible(NKFFTmin,self.iRvec)
        return NKFFTmin

    def set_symmetry(self,symmetry_gen):
        self.symgroup=Group(symmetry_gen,recip_lattice=self.recip_lattice,real_lattice=self.real_lattice)


    @lazy_property.LazyProperty
    def cRvec(self):
        return self.iRvec.dot(self.real_lattice)

    @property 
    def nRvec(self):
        return self.iRvec.shape[0]


    @lazy_property.LazyProperty
    def cell_volume(self):
        return abs(np.linalg.det(self.real_lattice))



    def __getMat(self,suffix):

        f=FF(self.seedname+"_" + suffix+"_R"+(".dat" if self.old_format else ""))
        MM_R=np.array([[np.array(f.read_record('2f8'),dtype=float) for m in range(self.num_wann)] for n in range(self.num_wann)])
        MM_R=MM_R[:,:,:,0]+1j*MM_R[:,:,:,1]
        f.close()
        ncomp=MM_R.shape[2]/self.nRvec0
        if ncomp==1:
            result=MM_R/self.Ndegen[None,None,:]
        elif ncomp==3:
            result= MM_R.reshape(self.num_wann, self.num_wann, 3, self.nRvec0).transpose(0,1,3,2)/self.Ndegen[None,None,:,None]
        elif ncomp==9:
            result= MM_R.reshape(self.num_wann, self.num_wann, 3,3, self.nRvec0).transpose(0,1,4,3,2)/self.Ndegen[None,None,:,None,None]
        else:
            raise RuntimeError("in __getMat: invalid ncomp : {0}".format(ncomp))
        if self.ws_map is None:
            return result
        else:
            return self.ws_map(result)
        

#
# the following  implements the use_ws_distance = True  (see Wannier90 documentation for details)
#



class map_1R():
   def __init__(self,lines,irvec):
       lines_split=[np.array(l.split(),dtype=int) for l in lines]
       self.dict={(l[0]-1,l[1]-1):l[2:].reshape(-1,3) for l in lines_split}
       self.irvec=np.array([irvec])
       
   def __call__(self,i,j):
       try :
           return self.dict[(i,j)]
       except KeyError:
           return self.irvec
          

class ws_dist_map():
        
    def __call__(self,matrix):
        ndim=len(matrix.shape)-3
        num_wann=matrix.shape[0]
        reshaper=(num_wann,num_wann)+(1,)*ndim
#        print ("check:",matrix.shape,reshaper,ndim)
        matrix_new=np.array([ sum(matrix[:,:,ir]*self._iRvec_new[irvecnew][ir].reshape(reshaper)
                                  for ir in self._iRvec_new[irvecnew] ) 
                                       for irvecnew in self._iRvec_ordered]).transpose( (1,2,0)+tuple(range(3,3+ndim)) )
        assert ( np.abs(matrix_new.sum(axis=2)-matrix.sum(axis=2)).max()<1e-12)
        return matrix_new

    def _add_star(self,ir,irvec_new,iw,jw):
        weight=1./irvec_new.shape[0]
        for irv in irvec_new:
            self._add(ir,irv,iw,jw,weight)


    def _add(self,ir,irvec_new,iw,jw,weight):
        irvec_new=tuple(irvec_new)
        if not (irvec_new in self._iRvec_new):
             self._iRvec_new[irvec_new]=dict()
        if not ir in self._iRvec_new[irvec_new]:
             self._iRvec_new[irvec_new][ir]=np.zeros((self.num_wann,self.num_wann),dtype=float)
        self._iRvec_new[irvec_new][ir][iw,jw]+=weight

    def _init_end(self,nRvec):
        self._iRvec_ordered=sorted(self._iRvec_new)
        for ir  in range(nRvec):
            chsum=0
            for irnew in self._iRvec_new:
                if ir in self._iRvec_new[irnew]:
                    chsum+=self._iRvec_new[irnew][ir]
            chsum=np.abs(chsum-np.ones( (self.num_wann,self.num_wann) )).sum() 
            if chsum>1e-12: print ("WARNING: Check sum for {0} : {1}".format(ir,chsum))



class ws_dist_map_read(ws_dist_map):
    def __init__(self,iRvec,num_wann,lines):
        nRvec=iRvec.shape[0]
        self.num_wann=num_wann
        self._iRvec_new=dict()
        n_nonzero=np.array([l.split()[-1] for l in lines[:nRvec]],dtype=int)
        lines=lines[nRvec:]
        for ir,nnz in enumerate(n_nonzero):
            map1r=map_1R(lines[:nnz],iRvec[ir])
            for iw in range(num_wann):
                for jw in range(num_wann):
                    self._add_star(ir,map1r(iw,jw),iw,jw)
            lines=lines[nnz:]
        self._init_end(nRvec)

        



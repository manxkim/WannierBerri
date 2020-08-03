#!/usr/bin/env python3


## these linesline if you want to use the git version of the code, instead of the one installed by pip
num_proc=4

import wannierberri as wberri

import numpy as np


SYM=wberri.symmetry

Efermi=np.linspace(18.1299,18.1300,2)
omega=np.linspace(0.0125,7.,560)
#omega=np.linspace(11.1299,21.1299,1001)

system=wberri.System_w90(seedname='pt',SHC=True,use_ws=False)

#generators=[SYM.Inversion,SYM.C4z,SYM.TimeReversal*SYM.C2x]
generators=[]
system.set_symmetry(generators)
#grid=wberri.Grid(system,length=100)
grid=wberri.Grid(system,NK=np.array([1,1,1]))

wberri.integrate(system,
            grid=grid,
            Efermi=Efermi, 
            omega=omega,
#            smearEf=0.1,
#            smearW=0.1,
            quantities=["opt_SHC"],
            numproc=num_proc,
            adpt_num_iter=0,
            fout_name='pt',
            restart=False,
            )

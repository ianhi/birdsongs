from syllable_class import *

class Song(Sillable):
    def __init__(self, file_name):
        fs, s = wavfile.read(file_name)
        if len(np.shape(s))>1 and s.shape[1]==2 :s = (s[:,1]+s[:,0])/2 # two channels to one
        
        self.NN       = 1024 
        self.overlap  = 1/1.1
        self.sigma    = self.NN/10
        self.umbral   = 0.05
        
        fu_all, tu_all, Sxx_all = get_spectrogram(s, fs, window=self.NN, overlap=self.overlap, sigma=self.sigma)
        
        self.fs       = fs
        self.s        = s
        self.envelope = normalizar(envelope_cabeza(self.s,intervalLength=0.01*self.fs), minout=0, method='extremos')
        self.time     = np.linspace(0, len(self.s)/self.fs, len(self.s))
        self.fu       = fu_all
        self.tu       = tu_all
        self.Sxx      = Sxx_all
        self.window_time = 0.005
        
        self.p = lmfit.Parameters()
        # add wi  : (NAME    VALUE  VARY   MIN    MAX  EXPR  BRUTE_STEP)
        self.p.add_many(('a0',   0.11,   False, 0,   0.25,   None, None), 
                        ('a1',    0.05,  False, -2,     2,  None, None),  
                        ('b0',    -0.1,  False, -1,   0.5,  None, None),  
                        ('b1',    1,     False,  0.2,   2,  None, None), 
                        ('gamma', 40000, False,  0.1,  1e5, None, None),
                        ('b2',    0.,    False, None, None, None, None), 
                        ('a2',    0.,    False, None, None, None, None))
        self.parametros = self.p.valuesdict()
        
        
        self.silabas = self.Silabas()
        
    def SilabaNo(self, no_silaba):
        self.no_silaba    = no_silaba
        ss                = self.silabas[no_silaba-1]  # silbido in indexes 
        silaba            = self.s[ss[0]:ss[-1]]       # silaba en audio
        self.silb_complet = silaba
        self.time_silaba  = self.time[ss[0]:ss[-1]]# -0.02/2
        self.t0           = self.time[ss[0]]
        self.silaba       = Sillable(self.silb_complet, self.fs, self.t0, self.window_time, self.p)
        
    # ------------- solver for some parameters -----------------
    def SolveSyllable(self, p):
        self.silaba.p = p
        self.silaba.AlphaBeta()
        self.silaba.BirdModel()
        
        deltaFF = np.abs(self.silaba.freq_amp_smooth_out - self.silaba.freq_amp_smooth)
        deltaSCI = np.abs(self.silaba.SCI_out-self.silaba.SCI)
        self.silaba.deltaSCI = deltaSCI#/np.max(deltaSCI)
        self.silaba.deltaFF  = 1e-4*deltaFF#/np.max(deltaFF)
        self.silaba.scoreSCI = np.sum(self.silaba.deltaSCI)/self.silaba.deltaSCI.size
        self.silaba.scoreFF  = np.sum(abs(self.silaba.deltaFF))/self.silaba.deltaFF.size
        
    # score functions, they are a real number (we are interest that both are one)    
    def residualSCI(self, p):
        self.SolveSyllable(p)
        return self.silaba.scoreSCI
    
    def residualFF(self, p):
        self.SolveSyllable(p)
        return self.silaba.scoreFF
    
    # ----------- OPTIMIZATION FUNCTIONS --------------
    def OptimalGamma(self, kwargs):
        start = time.time()
        self.silaba.p["gamma"].set(vary=True)
        
        mi    = lmfit.minimize(self.residualSCI, self.silaba.p, nan_policy='omit', **kwargs) 
        
        self.silaba.p["gamma"].set(value=mi.params["gamma"].value, vary=False)
        #self.silaba.params["gamma"] = mi.params["gamma"].value   # opt_gamma
        end   = time.time()
        print("γ* =  {0:.4f}".format(self.silaba.p["gamma"].value))
        
        
        return end-start #t_exe
    
    def OptimalBs(self, kwargs):
        # ---------------- b0--------------------
        start0 = time.time()
        self.silaba.p["b0"].set(vary=True)
        mi0    = lmfit.minimize(self.residualFF, self.silaba.p, nan_policy='omit', **kwargs) #, max_nfev=500) #dual_annealing # , Ns=200
        self.silaba.p["b0"].set(vary=False, value=mi0.params["b0"].value)
        #self.silaba.params["b0"] = mi0.params["b0"].value
        end0   = time.time()
        print("b_0*={0:.4f}".format(self.silaba.p["b0"].value))
        # ---------------- b1--------------------
        start1 = time.time()
        self.silaba.p["b1"].set(vary=True)
        mi1    = lmfit.minimize(self.residualFF, self.silaba.p, nan_policy='omit', **kwargs) 
        self.silaba.p["b1"].set(vary=False, value=mi1.params["b1"].value)
        #self.params["b1"] = mi1.params["b1"].value
        end1   = time.time()
        print("b_1*={0:.4f}".format(self.p["b1"].value))
        
        return [end0-start0, end1-start1]
    
    def Chunck(self, no_chunck):
        self.no_chunck     = no_chunck
        chunks_s, chunks_t = Windows(self.silb_complet, self.time_silaba, self.fs, window_time=0.02, overlap=1) # overla=1 not overlap
        self.chunck        = Sillable(chunks_s[no_chunck], self.fs, self.t0, self.window_time, self.p)#0.005)
        self.chunck.t0     = chunks_t[no_chunck][0]
        
        
        
    def Plot(self, file_name, flag=0): #flag = 1 or 0
        fig, ax = plt.subplots(3, 1, figsize=(12, 9))#, sharex=True, gridspec_kw={'width_ratios': [1, 1]})
        fig.subplots_adjust(hspace=0.4)
        
        ax[0].pcolormesh(self.tu, self.fu/1000, np.log(self.Sxx), cmap=plt.get_cmap('Greys'), rasterized=True)
        ax[0].plot(self.silaba.time_inter+self.t0, self.silaba.freq_amp_smooth*1e-3, 'b-', label='FF'.format(self.silaba.fs), lw=2)
        ax[0].plot(self.silaba.time_ampl+self.t0, self.silaba.freq_amp*1e-3, 'r+', label='sampled FF', ms=2)
        for ss in self.silabas:   ax[0].plot([self.time[ss[0]], self.time[ss[-1]]], [0, 0], 'k', lw=5)
        
        ax[0].set_ylim(0, 12.000); ax[0].set_xlim(min(self.time), max(self.time));
        ax[0].set_title("Complete Song Spectrum"); 
        ax[0].set_xlabel('t (s)'); ax[0].set_ylabel('f (kHz)')

        ax[1].plot(self.time, self.s/np.max(self.s),'k', label='audio')
        ax[1].plot(self.time, np.ones(len(self.time))*self.umbral, '--', label='umbral')
        ax[1].plot(self.time, self.envelope, label='envelope')
        ax[1].legend()#loc=1, title='Data')
        ax[1].set_title("Complete Song Sound Wave")
        ax[1].set_xlabel('t (s)'); ax[1].set_ylabel('Amplitud normalaized');
        ax[1].sharex(ax[0])

        if flag==1:
            #ax[2].pcolormesh(self.tu, self.fu, np.log(self.Sxx), cmap=plt.get_cmap('Greys'), rasterized=True)
            ax[0].plot(self.chunck.time_inter+self.chunck.t0, self.chunck.freq_amp_smooth*1e-3, 'g-', label='Chunck', lw=4)
            ax[2].plot(self.chunck.time_inter+self.chunck.t0, self.chunck.freq_amp_smooth*1e-3, 'g-', label='Chunck', lw=10)
        
        ax[2].pcolormesh(self.silaba.tu+self.t0, self.silaba.fu*1e-3, np.log(self.silaba.Sxx), cmap=plt.get_cmap('Greys'), rasterized=True) 
        ax[2].plot(self.silaba.time_inter+self.t0, self.silaba.freq_amp_smooth*1e-3, 'b-', lw=5, label='Smoothed and Interpolated\nto {0}=fs'.format(self.silaba.fs))
        ax[2].plot(self.silaba.time_ampl+self.t0, self.silaba.freq_amp*1e-3, 'r+', label='sampled FF', ms=3)
        ax[2].set_ylim((2, 11)); 
        ax[2].set_xlim((self.silaba.time_inter[0]-0.001+self.t0, self.silaba.time_inter[-1]+0.001+self.t0));
        ax[2].legend()
        ax[2].set_xlabel('t (s)'); ax[2].set_ylabel('f (khz)')
        ax[2].set_title('Single Syllable Spectrum, No {}'.format(self.no_silaba))
        
        ax[0].legend()
        fig.suptitle('Audio: {}'.format(file_name[39:]), fontsize=20)#, family='fantasy')
        print('Number of syllables {}'.format(len(self.silabas)))
        
        
    def Silabas(self):
        supra    = np.where(self.envelope > self.umbral)[0]
        silabas  = consecutive(supra, min_length=100)

        return [ss for ss in silabas if len(ss) > 1024] # elimino silabas cortas
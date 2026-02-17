import numpy as np
import matplotlib.pyplot as plt

fs = 1000 # Hz or cycles/second
t_period = 1 # seconds
N = t_period * fs # samples

t = np.linspace(0, t_period, N) # from 0 to t_period divided into N chunks

fund = 3
f = np.sin(2 * np.pi * fund * t)
for i in range(2,50):
    if i % 2 == 0: 
        continue
    f += 1/i * np.sin(2 * np.pi * i * fund * t)
# sig2 = 0.9 * np.sin(2 * np.pi * 3 * t)
# sig3 = 0.8 * np.sin(2 * np.pi * 5 * t)
# sig4 = 0.7 * np.sin(2 * np.pi * 7 * t)
# sig5 = 0.6 * np.sin(2 * np.pi * 9 * t)

# f = sig1 + sig2 + sig3 + sig4 + sig5

fig, ax = plt.subplots(nrows=4, ncols=1)

# plt.plot(t, sig1, label="sig1")
# plt.plot(t, sig2, label="sig2")
ax[0].plot(t, f, label="f")
ax[0].legend()

a = np.fft.rfft(f) # take the discrete fourier transform
freq_bins = np.fft.rfftfreq(N, 1/fs) # get the frequency of each bin in Hz

ax[1].plot(freq_bins, np.abs(a))
ax[1].legend()

ax[2].plot(freq_bins, np.abs(a))
ax[2].legend()

f2 = np.fft.irfft(a)
ax[3].plot(t, f2, label="f2")
ax[3].legend()

plt.tight_layout()
plt.show()

% Load in the gamma_curve data. Compute new inverse gamma table for
% psychtoolbox
clear all
close all

gammaData=readmatrix('gamma_curve.csv','NumHeaderLines',1)
wl=readmatrix('wavelengths.csv')
sp=readmatrix('modelspectra.csv')


% We are going to use FitGamma (and assume an actual gamma fucntion)
gamma_inputLevels=gammaData(:,1);
gamma_outputLevels=gammaData(:,2:4);
[nPoints,nGuns]=size(gamma_outputLevels);
normalizedInputLevels=(gamma_inputLevels+1)/2;
gamma_outputLevels=gamma_outputLevels-repmat(gamma_outputLevels(1,:),nPoints,1)

figure(1);
subplot(2,1,1);
hold off

subplot(2,1,2);
hold off
figure(2);
hold off
colorNames={'r','g','b'};
for thisGun=1:nGuns
   
    % Fit simple gamma power function
    output = linspace(0,1,256)';
    normOutput=gamma_outputLevels(:,thisGun)./max(gamma_outputLevels(:,thisGun))
    figure(1);
    subplot(2,1,1);
    hold on
    plot(normalizedInputLevels,normOutput,colorNames{thisGun})
    [extendedFit,extendedX] = FitGamma(normalizedInputLevels,normOutput,output,2);
    invertedInput = InvertGammaExtP(extendedX,1,normOutput);
    invertedGammaTableEntry=InvertGammaExtP(extendedX,1,output);

    subplot(2,1,2);
    plot(output,extendedFit,colorNames{thisGun});
    hold on;
    figure(2);
    plot(normOutput,invertedInput,colorNames{thisGun});
    hold on
    figure(3);
    plot(0:255,invertedGammaTableEntry,colorNames{thisGun});
    invertedGammaTable(:,thisGun)=invertedGammaTableEntry;
    hold on
    fprintf(1,'Found exponent %g\n\n',extendedX(1));
end

writematrix(invertedGammaTable,'vpixxGammaCorrect_20250121.csv')

% Also write out a file that contains the spectra data: From 390 to 780nm
% in steps of 1nm (so 391 meaurements - just like the fundamentals).
%%
figure(10);
plot(wl,sp)
% To match the spectral data we want 391 1nm samples between 390 and 780nm
% inclusive
reqWl=390:780;
LEDs=zeros(length(reqWl),3);
for thisLED=1:3
    LEDs(:,thisLED)=interp1(wl',sp(:,thisLED),reqWl');
end
plot(reqWl,LEDs)

comment='Vpixx spectra from python code measureGamma.py'
save('VPixxIrrad_20250121.mat','LEDs','reqWl','comment');
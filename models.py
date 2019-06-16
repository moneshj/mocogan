# coding: utf-8

## Additions for integration with UCF-101
import os
import math
import imageio
import skvideo.io
import numpy as np
from glob import glob
from torch.utils.data import Dataset
#### End of additions.


import torch
import torch.nn as nn
from torch.autograd import Variable
import torch.nn.init as init


# see: _netD in https://github.com/pytorch/examples/blob/master/dcgan/main.py
class Discriminator_I(nn.Module):
    def __init__(self, nc=3, ndf=64, ngpu=1):
        super(Discriminator_I, self).__init__()
        self.ngpu = ngpu
        self.main = nn.Sequential(
            # input is (nc) x 96 x 96
            nn.Conv2d(nc, ndf, 4, 2, 1, bias=False),
            nn.LeakyReLU(0.2, inplace=True),
            # state size. (ndf) x 48 x 48
            nn.Conv2d(ndf, ndf * 2, 4, 2, 1, bias=False),
            nn.BatchNorm2d(ndf * 2),
            nn.LeakyReLU(0.2, inplace=True),
            # state size. (ndf*2) x 24 x 24
            nn.Conv2d(ndf * 2, ndf * 4, 4, 2, 1, bias=False),
            nn.BatchNorm2d(ndf * 4),
            nn.LeakyReLU(0.2, inplace=True),
            # state size. (ndf*4) x 12 x 12
            nn.Conv2d(ndf * 4, ndf * 8, 4, 2, 1, bias=False),
            nn.BatchNorm2d(ndf * 8),
            nn.LeakyReLU(0.2, inplace=True),
            # state size. (ndf*8) x 6 x 6
            nn.Conv2d(ndf * 8, 1, 6, 1, 0, bias=False),
            nn.Sigmoid()
        )

    def forward(self, input):
        if isinstance(input.data, torch.cuda.FloatTensor) and self.ngpu > 1:
            output = nn.parallel.data_parallel(self.main, input, range(self.ngpu))
        else:
            output = self.main(input)

        return output.view(-1, 1).squeeze(1)


class Discriminator_V(nn.Module):
    def __init__(self, nc=3, ndf=64, T=16, ngpu=1, nClasses= 102):
        super(Discriminator_V, self).__init__()
        self.ngpu = ngpu
        
        self.label_sequence = nn.Sequential(
            nn.Embedding( nClasses, nClasses // T ),
            nn.Linear( nClasses // T, int((ndf*8)*(T/16)*6*6) ),
            nn.LeakyReLU( 0.2, inplace= True )
        )
        
        self.main = nn.Sequential(
            # input is (nc) x T x 96 x 96
            nn.Conv3d(nc, ndf, 4, 2, 1, bias=False),
            nn.LeakyReLU(0.2, inplace=True),
            # state size. (ndf) x T/2 x 48 x 48
            nn.Conv3d(ndf, ndf * 2, 4, 2, 1, bias=False),
            nn.BatchNorm3d(ndf * 2),
            nn.LeakyReLU(0.2, inplace=True),
            # state size. (ndf*2) x T/4 x 24 x 24
            nn.Conv3d(ndf * 2, ndf * 4, 4, 2, 1, bias=False),
            nn.BatchNorm3d(ndf * 4),
            nn.LeakyReLU(0.2, inplace=True),
            # state size. (ndf*4) x T/8 x 12 x 12
            nn.Conv3d(ndf * 4, ndf * 8, 4, 2, 1, bias=False),
            nn.BatchNorm3d(ndf * 8),
            nn.LeakyReLU(0.2, inplace=True),
            # state size. (ndf*8) x T/16  x 6 x 6
            Flatten(),
            #nn.Linear(int((ndf*8)*(T/16)*6*6), 1),
            #nn.Sigmoid()
        )
        
        self.final_sequence = nn.Sequential(
            nn.Linear(int((ndf*8)*(T/16)*6*6) * 2, 1),
            nn.Sigmoid()
        )

    def forward(self, input, labels):
    
        if isinstance(input.data, torch.cuda.FloatTensor) and self.ngpu > 1:
            labels = nn.parallel.data_parallel(self.label_sequence, labels, range(self.ngpu))
            intermediate_output = nn.parallel.data_parallel(self.main, input, range(self.ngpu))
            output = nn.parallel.data_parallel(self.final_sequence, torch.cat((intermediate_output, labels), 1), range(self.ngpu))
            
        else:
            # labels => 16 x 18432 || 1 x 18432
            labels = self.label_sequence(labels)
            # intermediate_output => 16 x 18432
            intermediate_output = self.main(input)
            # cat to be => 16 x 18432*2
            output = self.final_sequence(torch.cat((intermediate_output, labels), 1))
        
        return output.view(-1, 1).squeeze(1)


# see: _netG in https://github.com/pytorch/examples/blob/master/dcgan/main.py
class Generator_I(nn.Module):
    def __init__(self, nc=3, ngf=64, nz=60, ngpu=1, nClasses= 102, batch_size= 16):
        super(Generator_I, self).__init__()
        self.ngpu = ngpu
        # Addition for Conditioning the Model
        # nClasses = #UCF-101 Action Class + 1 (Fake Class) 
        self.label_sequence = nn.Sequential(
            # labels size [ NumClasses / 16 ]
            nn.Embedding(nClasses, nClasses//16),
            nn.Linear(nClasses//16, nz),
            nn.ReLU(True)
        )
        
        self.combine_sequence = nn.Sequential(
            nn.Linear(ngf*4 + batch_size, ngf*4)
        )
        
        self.main = nn.Sequential(
            # input is Z, going into a convolution
            nn.ConvTranspose2d(     nz, ngf * 8, 6, 1, 0, bias=False),
            nn.BatchNorm2d(ngf * 8),
            nn.ReLU(True),
            # state size. (ngf*8) x 6 x 6
            nn.ConvTranspose2d(ngf * 8, ngf * 4, 4, 2, 1, bias=False),
            nn.BatchNorm2d(ngf * 4),
            nn.ReLU(True),
            # state size. (ngf*4) x 12 x 12
            nn.ConvTranspose2d(ngf * 4, ngf * 2, 4, 2, 1, bias=False),
            nn.BatchNorm2d(ngf * 2),
            nn.ReLU(True),
            # state size. (ngf*2) x 24 x 24
            nn.ConvTranspose2d(ngf * 2,     ngf, 4, 2, 1, bias=False),
            nn.BatchNorm2d(ngf),
            nn.ReLU(True),
            # state size. (ngf) x 48 x 48
            nn.ConvTranspose2d(    ngf,      nc, 4, 2, 1, bias=False),
            nn.Tanh()
            # state size. (nc) x 96 x 96
        )

    def forward(self, input, labels):
        if isinstance(input.data, torch.cuda.FloatTensor) and self.ngpu > 1:
            # Addition to prepare labels to be concatenated with input.
            labels = nn.parallel.data_parallel(self.label_sequence, labels, range(self.ngpu))
            labels = labels.unsqueeze(0).unsqueeze(0)
            labels = labels.transpose(0,2).transpose(1,3)
            input[-1] = labels
            
            output = nn.parallel.data_parallel(self.main, input, range(self.ngpu))
            
        else:
            labels = self.label_sequence(labels)
            labels = labels.unsqueeze(0).unsqueeze(0)
            labels = labels.transpose(0,2).transpose(1,3)
            combinedInput = torch.cat((input, labels), 0).transpose(0,3)
            
            input = self.combine_sequence(combinedInput).transpose(3,0)
            
            output = self.main(input)
            
        return output


class GRU(nn.Module):
    def __init__(self, input_size, hidden_size, dropout=0, gpu=True):
        super(GRU, self).__init__()

        output_size      = input_size
        self._gpu        = gpu
        self.hidden_size = hidden_size

        # define layers
        self.gru    = nn.GRUCell(input_size, hidden_size)
        self.drop   = nn.Dropout(p=dropout)
        self.linear = nn.Linear(hidden_size, output_size)
        self.bn     = nn.BatchNorm1d(output_size, affine=False)

    def forward(self, inputs, n_frames):
        '''
        inputs.shape()   => (batch_size, input_size)
        outputs.shape() => (seq_len, batch_size, output_size)
        '''
        outputs = []
        for i in range(n_frames):
            self.hidden = self.gru(inputs, self.hidden)
            inputs = self.linear(self.hidden)
            outputs.append(inputs)
        outputs = [ self.bn(elm) for elm in outputs ]
        outputs = torch.stack(outputs)
        return outputs

    def initWeight(self, init_forget_bias=1):
        # See details in https://github.com/pytorch/pytorch/blob/master/torch/nn/modules/rnn.py
        for name, params in self.named_parameters():
            if 'weight' in name:
                init.xavier_uniform(params)

            # initialize forget gate bias
            elif 'gru.bias_ih_l' in name:
                b_ir, b_iz, b_in = params.chunk(3, 0)
                init.constant(b_iz, init_forget_bias)
            elif 'gru.bias_hh_l' in name:
                b_hr, b_hz, b_hn = params.chunk(3, 0)
                init.constant(b_hz, init_forget_bias)
            else:
                init.constant(params, 0)

    def initHidden(self, batch_size):
        self.hidden = Variable(torch.zeros(batch_size, self.hidden_size))
        if self._gpu == True:
            self.hidden = self.hidden.cuda()


''' utils '''

class Flatten(nn.Module):
    def forward(self, input):
        return input.view(input.size(0), -1)


## Addition for loading target & videoPath from UCF-101 class.
   

def getNumFrames(reader):
    
    try:
        return math.ceil(reader.get_meta_data()['fps'] * reader.get_meta_data()['duration'])
    
    except AttributeError as _:
        filename = reader
        return getNumFrames(imageio.get_reader(filename,  'ffmpeg'))

def readVideoImageio(filename, n_channels= 3):
    
    with imageio.get_reader(filename,  'ffmpeg') as reader:
    
        nframes = getNumFrames(reader)
        shape = reader.get_meta_data()['size']
        
        videodata = np.empty((nframes, shape[0], shape[1], n_channels))
        
        for idx, img in enumerate(reader):
            videodata[idx, :, :, :] = img
         
    # Paranoid double check
    if not reader.closed:
        reader.close()
            
    return videodata

def has_file_allowed_extension(filename, extensions):
    """Checks if a file is an allowed extension.

    Args:
        filename (string): path to a file
        extensions (tuple of strings): extensions to consider (lowercase)

    Returns:
        bool: True if the filename ends with one of given extensions
    """
    extensions = list(extensions)
    
    returnValue = False
    for extension in extensions:
        returnValue = returnValue or filename.lower().endswith(extension)
    
    return returnValue


def make_dataset(dir, class_to_idx, extensions=None):
    videos = []
    dir = os.path.expanduser(dir)
    
    if extensions is not None:
        def is_valid_file(x):
            return has_file_allowed_extension(x, extensions)
        
    for target in sorted(class_to_idx.keys()):
        d = os.path.join(dir, target)
        if not os.path.isdir(d):
            continue
        for root, _, fnames in sorted(os.walk(d)):
            for fname in sorted(fnames):
                path = os.path.join(root, fname)
                if is_valid_file(path):
                    item = (path, class_to_idx[target])
                    videos.append(item)
                    
    return videos

def loadDict(filepath):
    dictClassesIdx = {}
    
    try:
        with open(filepath) as file:
            for line in file:
                dictClassesIdx[ line.split() [1]] = int( line.split() [0] )
            
    except FileNotFoundError as error:
        print(error)
        
    return dictClassesIdx

## Addition for loading videos avoiding to get Out Of Memory

class UCF_101(Dataset):
    """
        Summary
        ----------
            A class that extends the abstract Dataset class to load lazily videos from disk.

        Parameters
        ----------

        rootDir: string
            Absolute path to the directory in which the subfolders of UCF-101 (named with "Action") are found.

        videoHandler: module
            Hook to add new module to handles video loading.
            
        supportedExtensions: List of Strings
            A list of extensions to load. E.g. ["mp4", "avi"]
            
        transform: torchvision.transforms.Compose
            Sequence of transformation to apply to the dataset while loading.
            
        Constructor:
        ----------
            It requires that the in the previous directory with respect to @Param rootDir it can find the directory ucfTrainTestList
            where it can read the file named classInd.txt where the mapping "Target" "Index" can be loaded.
            
        Attributes:
        ----------
            videoLengths: 
                A dictionary that contains as key the filepath and as value the nframes of the video.
                This is populated in a lazy way, every time that a video is loaded for the first time into memory.
        
    """    
    
    def __init__(self, rootDir, videoHandler = readVideoImageio, supportedExtensions= [], transform= None):
        
        ucfDictFilename = "classInd.txt"                    #Used to load the file classes.
        ucfTrainTestDirname = "ucfTrainTestlist"            #Used to find the class file.
        previousDir = [*(os.path.split(rootDir)[:-1])][0]
        
        self.dictPath = os.path.join(previousDir, ucfTrainTestDirname, ucfDictFilename)
        self.rootDir = os.path.join(os.path.dirname(__file__), rootDir)
        self.videoHandler = videoHandler
        self.transform = transform
        self.videoLengths = {}
        
        self.class_to_idx = loadDict(self.dictPath)
        
        self.samples= make_dataset(self.rootDir, self.class_to_idx, supportedExtensions)
        


    def __len__(self):
        return len(self.samples)


    def __getitem__(self, index):
        
        path, target = self.samples[index]
        
        #readVideo = self.videoHandler(path, verbosity= 1)
        #readVideo = self.videoHandler(path, verbosity= 1)
        
        """
        inputdict = {"-threads": "1", "-s": "96x96"}
        
        reader = FFmpegReader(path, inputdict= inputdict, verbosity= 1)
        T, M, N, C = reader.getShape()

        readVideo = np.empty((T, M, N, C), dtype=reader.dtype)
        for idx, frame in enumerate(reader.nextFrame()):
            readVideo[idx, :, :, :] = frame

        reader.close()
        """
        
        readVideo = self.videoHandler(path)
        self.videoLengths[path] = getNumFrames(path)
        
        if self.transform:
            readVideo = self.transform(readVideo)
        
        return readVideo, target


#### End of Addition.

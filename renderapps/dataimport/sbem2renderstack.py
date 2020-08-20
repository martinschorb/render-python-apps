import os
import renderapi
from renderapi.tilespec import TileSpec, Layout
from renderapi.image_pyramid import ImagePyramid, MipMapLevel

from renderapi.transform import AffineModel
from renderapps.dataimport.create_mipmaps import create_mipmaps
my_env = os.environ.copy()
from renderapps.module.render_module import RenderModule, RenderParameters
from argschema.fields import InputFile, InputDir, Str, Int, Boolean
import pandas as pd

import glob
import bdv_tools as bdv
from pyEM import parse_adoc
import numpy as np

    
    
    
example_input={
    #"statetableFile" : "/nas/data/M246930_Scnn1a_4_f1//scripts/statetable_ribbon_0_session_0_section_3",
    #"projectDirectory" : "/nas/data/M246930_Scnn1a_4_f1/",
    #"outputStackPrefix" : "Acquisition",
    #"pool_size" : 20,
    "delete_stack" : False
}



def groupsharepath(f1):

    import subprocess
    import os
    import sys

    if os.name=='nt':
            p=subprocess.Popen('net use',stdout=subprocess.PIPE)
            n_use=p.communicate()[0].decode(encoding='ansi')
            drive=f1[:f1.find(':\\')+1]
            
            if drive:
                    shareline = n_use[n_use.find(drive):]
                    shareline = shareline[:shareline.find('\n')]
                    shareline1 = shareline[shareline.rfind('\\')+1:]
                    share = shareline1[:shareline1.find(' ')]		
                    file1 = f1[f1.find(drive)+3:]
                    
            else:
                    share1 = f1[f1.find('\\\\')+2:]
                    share = share1[:share1.find('\\')]	
                    f2 = f1[f1.rfind(share):]
                    file1 = f2[f2.find('\\')+1:]
                    
            file1 = file1.replace('\\','/')
            file1 = '/g/'+share+'/'+file1

    if sys.platform=='darwin':
        file1=f1.replace('Volumes','g')\

    if 'linux' in sys.platform:
        file1=f1

    return(file1)



class CreateFastStacksParameters(RenderParameters):
    projectDirectory = InputDir(required=True,
        description='path to project root')
    pool_size = Int(require=False,default=20,
        description='number of parallel threads to use')
    delete_stack = Boolean(require=False,default=True,
        description='flag to decide whether stack should be deleted before new upload')




def make_tilespec_from_sbemimage (rootdir,outputProject,outputOwner,outputStack,minval=0,maxval=50000):

    mipmap_args = []
    tilespecpaths = []
        
        
    if not os.path.exists('meta'): print('Change to proper directory!');exit()
    
    
    
    
    mfile0 = os.path.join('meta','logs','imagelist_')
    
    mfiles = glob.glob(mfile0+'*')
    
    tiles = list()
    views = list()
    
    idx = 0
    
    for mfile in mfiles:
        
        with open(mfile) as mf: ml = mf.read().splitlines()
        
        mdfile = os.path.join('meta','logs','metadata'+mfile[mfile.rfind('_'):])
        
        with open(mdfile) as mdf: mdl = mdf.read().splitlines()
        
        conffile = os.path.join('meta','logs','config'+mfile[mfile.rfind('_'):])
        
        with open(conffile) as cf: cl = cf.read().splitlines()
        
        config = parse_adoc(cl)
        
        
        pxs = float(config['grab_frame_pixel_size'][0])#/1000  # in um
        z_thick = float(config['slice_thickness'][0])#/1000  # in um
        
        
         # generate the individual transformation matrices
         # 1)  The scale and rotation information form the map item
        mat = np.diag((pxs,pxs,z_thick))
        
        mat_s = np.concatenate((mat,[[0],[0],[0]]),axis=1)
        mat_s = np.concatenate((mat_s,[[0,0,0,1]]))
        
        tilespeclist=[]
        z=0
        
        for line in mdl:
            if line.startswith('TILE: '):
                tile = bdv.str2dict(line[line.find('{'):])
                tiles.append(tile)
                
           # 2) The translation matrix to position the object in space (lower left corner)
                mat_t = np.concatenate((np.eye(3),[[tile['glob_x']],[tile['glob_y']],[tile['glob_z']]]),axis=1)
                mat_t = np.concatenate((mat_t,[[0,0,0,1]]))                
                
                f1 = os.path.realpath(tile['filename'])
                
                fbase = os.path.splitext(os.path.basename(f1))[0]
                
                tilespecdir = os.path.join('processed','tilespec')
            
            
                filepath= groupsharepath(f1)
                
                
                
                #print tilespecdir
                if not os.path.isdir(tilespecdir):
                    os.makedirs(tilespecdir)
                    
                downdir = os.path.join("processed","downsamp_images")
                #print "This is the Down Sampled Directory: %s"%downdir

                if not os.path.exists(downdir):
                    os.makedirs(downdir)
                    
                downdir1 = groupsharepath(os.path.realpath(downdir))

                #construct command for creating mipmaps for this tilespec
                #downcmd = ['python','create_mipmaps.py','--inputImage',filepath,'--outputDirectory',downdir,'--mipmaplevels','1','2','3']
                #cmds.append(downcmd)
                mipmap_args.append((f1,os.path.realpath(downdir)))
                layout = Layout(sectionId=tile['slice_counter'],
                                                scopeId='3View',
                                                cameraId='3View',
                                                imageRow=0,
                                                imageCol=0,
                                                stageX = tile['glob_x'],
                                                stageY = tile['glob_y'],
                                                rotation = 0.0,
                                                pixelsize = pxs/10)

                mipmap0 = MipMapLevel(level=0,imageUrl='file://' + filepath)
                mipmaplevels=[mipmap0]
                filename = tile['tileid']

                for i in range(1,4):
                    scUrl = 'file://' + os.path.join(downdir1,fbase) + '_mip0%d.jpg'%i
                    mml = MipMapLevel(level=i,imageUrl=scUrl)
                    mipmaplevels.append(mml)

                tform = AffineModel(M00=1,
                                         M01=0,
                                         M10=0,
                                         M11=1,
                                         B0=tile['glob_x'],
                                         B1=tile['glob_y'])

                tilespeclist.append(TileSpec(tileId=tile['tileid'],
                                     frameId = tile['tileid'][:tile['tileid'].find('.')],
                                     z=tile['glob_z'],
                                     width=tile['tile_width'],
                                     height=tile['tile_height'],
                                     mipMapLevels=mipmaplevels,
                                     tforms=[tform],
                                     minint=minval,
                                     maxint=maxval,
                                     layout= layout))
                z = tile['glob_z']



                json_file = os.path.realpath(os.path.join(tilespecdir,outputProject+'_'+outputOwner+'_'+outputStack+'_%04d.json'%z))
                fd=open(json_file, "w")
                renderapi.utils.renderdump(tilespeclist,fd,sort_keys=True, indent=4, separators=(',', ': '))
                fd.close()
                tilespecpaths.append(json_file)
    return tilespecpaths,mipmap_args

def create_mipmap_from_tuple(mipmap_tuple):
    (filepath,downdir)=mipmap_tuple
    return create_mipmaps(filepath,downdir)


###


###   CALL THE FUNCTIONS
rootdir = os.getcwd()
outputProject = SBEM_test1
outputProject = 'SBEM_test1'
outputOwner = 'SBEM'
outputStack = 'platy_200527'


# make tilespecs
tilespecpaths,mipmap_args = make_tilespec_from_sbemimage(rootdir,outputProject,outputOwner,outputStack)

# generate mipmaps
with renderapi.client.WithPool(8) as pool:
    results=pool.map(create_mipmap_from_tuple,mipmap_args)

#connect to render server
render1 = renderapi.connect(host='localhost',port=8080,owner=outputOwner,project=outputProject,client_scripts='/home/schorb/render/render-ws-java-client/src/main/scripts')


#upload metadata to render server
renderapi.client.import_jsonfiles(outputStack,tilespecpaths,render=render1, poolsize=8)




class CreateFastStack(RenderModule):
    def __init__(self,schema_type=None,*args,**kwargs):
        if schema_type is None:
            schema_type = CreateFastStacksParameters

        super(CreateFastStack,self).__init__(schema_type=schema_type,*args,**kwargs)
    def run(self):
        outputProject=self.args['render']['project']
        outputOwner = self.args['render']['owner']
        rootdir = self.args['projectDirectory']

        # print "This is delete stack : "
        # print self.args['delete_stack']
        # #exit(0)
        # df = pd.read_csv(statetablefile)
        # ribbons = df.groupby('ribbon')
        # k=0
        # for ribnum,ribbon in ribbons:
        #     mydf = ribbon.groupby('ch_name')
        #     for channum,chan in mydf:
                
                
                outputStack = self.args['outputStackPrefix'] + '_%s'%(channum)

                self.logger.info("creating tilespecs and cmds....")
                tilespecpaths,mipmap_args = make_tilespec_from_statetable(chan,rootdir,outputProject,outputOwner,outputStack)
                self.logger.info("importing tilespecs into render....")
                self.logger.info("creating downsampled images ...")
                with renderapi.client.WithPool(self.args['pool_size']) as pool:
                    results=pool.map(create_mipmap_from_tuple,mipmap_args)

                #groups = [(subprocess.Popen(cmd,\
                # stdout=subprocess.PIPE) for cmd in cmds)] \
                # * self.args['pool_size'] # itertools' grouper recipe
                #for processes in izip_longest(*groups): # run len(processes) == limit at a time
                #   for p in filter(None, processes):
                #        p.wait()
                self.logger.info("uploading to render ...")
                if k==0:
                    if self.args['delete_stack']:
                        renderapi.stack.delete_stack(outputStack,owner=outputOwner,project=outputProject,render=self.render)

                    renderapi.stack.create_stack(outputStack,owner=outputOwner,
                    project=outputProject,verbose=False,render=parameters)
                self.logger.info(tilespecpaths)
                renderapi.client.import_jsonfiles(outputStack,tilespecpaths,render=self.render, poolsize=self.args['pool_size'])
            k+=1

if __name__ == "__main__":
    #mod = CreateFastStack(schema_type = CreateFastStacksParameters)
    #print example_input
    mod = CreateFastStack(input_data=example_input,schema_type=CreateFastStacksParameters)
    mod.run()


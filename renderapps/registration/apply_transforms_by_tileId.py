import renderapi
from functools import partial
import tempfile
from ..module.render_module import RenderModule,RenderParameters
from argschema.fields import Str, Int
import numpy as np

# "Apply set of alignmnet transformations derived by EM aligner \
#         or any alignmnet pipeline where there are seperate transforms for every tile, \
#         replacing the transforms in another stack for which there is a 1>1 correspondance between the tiles\
#         such that alignments can be applied to other channels taken at the same time\
#         note that tiles that do not exist within the aligned stack, but do in the non-aligned input stack\
#         will be dropped in this process. Conversely, tiles that exist in the aligned stack but do not exist in the non-aligned\
#         but do not exist in the non-aligned stack will be dropped")

example_json={
        "render":{
            "host":"ibs-forrestc-ux1",
            "port":80,
            "owner":"Forrest",
            "project":"M246930_Scnn1a_4_f1",
            "client_scripts":"/pipeline/render/render-ws-java-client/src/main/scripts"
        },
        "alignedStack":"Fine_Aligned_Deconvolved_1_DAPI_1_filtered",
        "inputStack":"REG_STI_DCV_FF_Session1",
        "outputStack":"FA_STI_DCV_FF_Session1",
        "pool_size":20
    }

class ApplyTransformParameters(RenderParameters):
    alignedStack = Str(required=True,
        description='stack whose transforms you want to copy')
    inputStack = Str(required=True,
        description='stack you want to apply transforms to')
    outputStack = Str(required=True,
        description='stack name to save result')
    pool_size =  Int(required=True,default=20,
        description='number of parallel threads')

def process_tilespecs(aligned_tilespecs,input_tilespecs):

    #use the function to make jsons for aligned and input stacks
    #aligned_tilespecs = render.run(renderapi.tilespec.get_tile_specs_from_z,alignedStack,z)
    #input_tilespecs = render.run(renderapi.tilespec.get_tile_specs_from_z,inputStack,z)
    
    #keep a list of tilespecs to output
    output_tilespecs = []
    #loop over all input tilespecs and their frame numbers
    for ts in input_tilespecs:
        #get a list of indices where the aligned_framenumbers match this frame number
        al_ts = [tsa for tsa in aligned_tilespecs if tsa.tileId==ts.tileId]

        #if there is a match
        if len(al_ts)>0:
            #take the first one (should be the only one)
            al_ts = al_ts[0]
            #modify its transforms to be the corresponding aligned transforms
            ts.tforms = al_ts.tforms
            #modify the z values to get the new z value
            ts.z = al_ts.z
            #add it to the list of output tilespecs
            output_tilespecs.append(ts)

    return output_tilespecs

class ApplyTransforms(RenderModule):
    def __init__(self,schema_type=None,*args,**kwargs):
        if schema_type is None:
            schema_type = ApplyTransformParameters
        super(ApplyTransforms,self).__init__(schema_type=schema_type,*args,**kwargs)
    def run(self):
        self.logger.debug(self.args)
        
        aligned_tilespecs =renderapi.tilespec.get_tile_specs_from_stack(self.args['alignedStack'],render=self.render)
        input_tilespecs = renderapi.tilespec.get_tile_specs_from_stack(self.args['inputStack'],render=self.render)
        output_tilespecs = process_tilespecs(aligned_tilespecs,input_tilespecs)
        
        #OLD CODE WAS RUN BY MATCHING Z VALUES... NEW CODE WORKS GLOBALLY.. WILL BREAK FOR LARGE STACKS.
        #STEP 2: get z values that exist in aligned stack
        #zvalues=self.render.run(renderapi.stack.get_z_values_for_stack,self.args['alignedStack'])
        #zvalues_input = self.render.run(renderapi.stack.get_z_values_for_stack,self.args['inputStack'])
        #zvalues = np.intersect1d(np.array(zvalues),np.array(zvalues_input))
        #STEP 3: go through z in a parralel way
        # at each z, call render to produce json files to pass into the stitching jar
        # run the stitching jar to produce a new json for that z
        #call the creation of this in a parallel way
        #mypartial = partial(process_z,self.render,self.args['alignedStack'],self.args['inputStack'],self.args['outputStack'])
        #with renderapi.client.WithPool(self.args['pool_size']) as pool:
        #    jsonFilePaths = pool.map(mypartial,zvalues)

        #upload the resulting stack to render
        self.render.run(renderapi.stack.create_stack,self.args['outputStack'])
        self.render.run(renderapi.client.import_tilespecs_parallel,
                        self.args['outputStack'],
                        output_tilespecs,
                        pool_size=self.args['pool_size'])
        self.render.run(renderapi.stack.set_stack_state,self.args['outputStack'],state='COMPLETE')
if __name__ == "__main__":
    mod = ApplyTransforms(input_data = example_json)
    mod.run()

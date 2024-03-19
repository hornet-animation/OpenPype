baking_output={'rec709':{'baking':'_rec709',
                         'publish':'_rec709'},
               'sRGB':{'baking':'_sRGB',
                       'publish':'_sRGB'},
               'proxy':{'baking':'_PRsrgb',
                        'publish':'_PRsrgb'}}



class NameFix:
    def fix_baking(self, file_path, color_space):
        if color_space.lower() == 'rec709':
            if '.baking.' in file_path:
                new_file = file_path.replace('.baking.', '.baking_rec709.')
                return new_file
            elif '.baking_rec709.' in file_path:
                new_file = file_path.replace('.baking_rec709.', '.baking_rec709.')
                return new_file
            elif '.baking_rec709_h264.' in file_path:
                new_file = file_path.replace('.baking_rec709_h264.', '.baking_rec709.')
                return new_file
        elif color_space.lower() == 'srgb':
            if '.baking.' in file_path:
                new_file = file_path.replace('.baking.', '.baking_sRGB.')
                return new_file
            elif '.baking_rec709.' in file_path:
                new_file = file_path.replace('.baking_rec709.', '.baking_sRGB.')
                return new_file
            elif '.baking_rec709_h264.' in file_path:
                new_file = file_path.replace('.baking_rec709_h264.', '.baking_sRGB.')
                return new_file
        elif color_space.lower() == 'proxy':
            if '.baking_h264.' in file_path:
                new_file = file_path.replace('.baking_h264.', '.baking_PRsrgb.')
                return new_file
            elif '.baking_rec709.' in file_path:
                new_file = file_path.replace('.baking_rec709.', '.baking_PRsrgb.')
                return new_file
            elif '.baking_rec709_h264.' in file_path:
                new_file = file_path.replace('.baking_rec709_h264.' ,'.baking_PRsrgb.')
                return new_file
            elif '.baking_PRsrgb.' in file_path:
                return file_path
        else:
            print("Invalid color space specified")
            return None
    def fix_publish(self, src_path,out_path):
        path_split = out_path.split('_v')
        if '_rec709.' in src_path:
            new_file = path_split[0]+'_rec709_v'+path_split[1]
            return new_file
        elif '_sRGB.' in src_path:
            new_file = path_split[0]+'_sRGB_v'+path_split[1]
            return new_file
        elif '_PRsrgb.' in src_path:
            new_file = path_split[0]+'_PRsrgb_v'+path_split[1]
            return new_file.replace('_h264','')
        elif '.baking_rec709_h264burnin.' in src_path:
            new_file = path_split[0]+'_PRsrgb_v'+path_split[1]
            return new_file.replace('_h264','')
        else:
            print("Missing colorspace token")
            return out_path

if __name__ == "__main__":
        fixer = NameFix()
        file_path = "P:/projects/internalTesting/JT_pype/sequences/0020/comp/work/renders/nuke/renderCompMain/renderCompMain.baking_sRGB.mov"
        out_path = "P:/projects/internalTesting/JT_pype/sequences/0020/publish/render/renderCompMain/v036/jt_pype_0020_renderCompMain_v036.mov"
        color_space = "rec709"
        result = fixer.fix_publish(file_path,out_path)
        print(result)

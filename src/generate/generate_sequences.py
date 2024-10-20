import os

import matplotlib.pyplot as plt
import torch
import numpy as np

from src.utils.get_model_and_data import get_model_and_data
from src.models.get_model import get_model

from src.parser.generate import parser
import src.utils.fixseed  # noqa

import src.utils.rotation_conversions as geometry #jw

plt.switch_backend('agg')


def generate_actions(beta, model, dataset, epoch, params, folder, num_frames=60,
                     durationexp=False, vertstrans=False, onlygen=False, nspa=10, inter=False, writer=None):
    """ Generate & viz samples """

    # visualize with joints3D
    model.outputxyz = True
    # print("remove smpl")
    # model.param2xyz["jointstype"] = "vertices"
    model.param2xyz["jointstype"] = "smpl"

    print(f"Visualization of the epoch {epoch}")

    fact = params["fact_latent"]
    num_classes = dataset.num_classes
    classes = torch.arange(num_classes)

    if not onlygen:
        nspa = 1

    nats = num_classes

    if durationexp:
        nspa = 4
        durations = [40, 60, 80, 100]
        gendurations = torch.tensor([[dur for cl in classes] for dur in durations], dtype=int)
    else:
        gendurations = torch.tensor([num_frames for cl in classes], dtype=int)

    if not onlygen:
        # extract the real samples
        real_samples, mask_real, real_lengths = dataset.get_label_sample_batch(classes.numpy())
        # to visualize directly

        # Visualizaion of real samples
        visualization = {"x": real_samples.to(model.device),
                         "y": classes.to(model.device),
                         "mask": mask_real.to(model.device),
                         "lengths": real_lengths.to(model.device),
                         "output": real_samples.to(model.device)}

        reconstruction = {"x": real_samples.to(model.device),
                          "y": classes.to(model.device),
                          "lengths": real_lengths.to(model.device),
                          "mask": mask_real.to(model.device)}

    print("Computing the samples poses..")

    # generate the repr (joints3D/pose etc)
    model.eval()
    with torch.no_grad():
        if not onlygen:
            # Get xyz for the real ones
            visualization["output_xyz"] = model.rot2xyz(visualization["output"],
                                                        visualization["mask"],
                                                        vertstrans=vertstrans,
                                                        beta=beta)

            # Reconstruction of the real data
            reconstruction = model(reconstruction)  # update reconstruction dicts

            noise_same_action = "random"
            noise_diff_action = "random"

            # Generate the new data
            generation = model.generate(classes, gendurations, nspa=nspa,
                                        noise_same_action=noise_same_action,
                                        noise_diff_action=noise_diff_action,
                                        fact=fact)

            generation["output_xyz"] = model.rot2xyz(generation["output"],
                                                     generation["mask"], vertstrans=vertstrans,
                                                     beta=beta)

            outxyz = model.rot2xyz(reconstruction["output"],
                                   reconstruction["mask"], vertstrans=vertstrans,
                                   beta=beta)
            reconstruction["output_xyz"] = outxyz
        else:
            if inter:
                noise_same_action = "interpolate"
            else:
                noise_same_action = "random"

            noise_diff_action = "random"

            # Generate the new data
            generation = model.generate(classes, gendurations, nspa=nspa,
                                        noise_same_action=noise_same_action,
                                        noise_diff_action=noise_diff_action,
                                        fact=fact)

            generation["output_xyz"] = model.rot2xyz(generation["output"],
                                                     generation["mask"], vertstrans=vertstrans,
                                                     beta=beta)
            # output = generation["output_xyz"].reshape(nspa, nats, *generation["output_xyz"].shape[1:]).cpu().numpy()
            output = generation["output_xyz"].reshape(nspa, nats, *generation["output_xyz"].shape[1:]).cpu().numpy()
            print(type(output))
            print(output.shape)
            output = generation["output"]
            print(type(output))
            print(output.shape)
            '''
            <class 'numpy.ndarray'>
            (10, 5, 22, 3, 60)
            <class 'torch.Tensor'>
            torch.Size([50, 24, 6, 60])

            '''
            # jw_6drot = output[0,0,:,0]
            # print(jw_6drot)

            # 텐서의 형태를 유지한채로 변환 수행
            B, P, _, F = output.shape

            # (50 * 24 * 60, 6) 형태로 변환
            flattened_tensor = output.permute(0, 1, 3, 2).reshape(-1, 6)

            # 6D 회전 벡터를 3x3 회전 행렬로 변환
            rot_matrices = geometry.rotation_6d_to_matrix(flattened_tensor)

            # 3x3 회전 행렬을 축-각(axis-angle) 표현으로 변환
            axis_angles = torch.stack([geometry.matrix_to_axis_angle(rot_matrix) for rot_matrix in rot_matrices])

            # (50, 24, 3, 60) 형태로 변환
            reshaped_axis_angles = axis_angles.view(B, P, F, 3).permute(0, 1, 3, 2)

            # 변환된 텐서 확인
            print(reshaped_axis_angles.shape)  # Expected shape: (50, 24, 3, 60)

            # (10, 5, 24, 3, 60) 형태로 변환
            final_tensor = reshaped_axis_angles.view(10, 5, 24, 3, 60)

            # NumPy ndarray로 변환
            final_array = final_tensor.numpy()

            # .npy 파일로 저장
            np.save('output.npy', final_array)

            print(f"Saved array shape: {final_array.shape}")

            exit()

    if not onlygen:
        output = np.stack([visualization["output_xyz"].cpu().numpy(),
                           generation["output_xyz"].cpu().numpy(),
                           reconstruction["output_xyz"].cpu().numpy()])

    return output


def main():
    parameters, folder, checkpointname, epoch = parser()
    nspa = parameters["num_samples_per_action"]

    # no dataset needed
    if parameters["mode"] in []:   # ["gen", "duration", "interpolate"]:
        model = get_model(parameters)
    else:
        model, datasets = get_model_and_data(parameters)
        dataset = datasets["train"]  # same for ntu

    print("Restore weights..")
    checkpointpath = os.path.join(folder, checkpointname)
    state_dict = torch.load(checkpointpath, map_location=parameters["device"])
    model.load_state_dict(state_dict)

    from src.utils.fixseed import fixseed  # noqa
    for seed in [1]:  # [0, 1, 2]:
        fixseed(seed)
        # visualize_params
        onlygen = True
        vertstrans = False
        inter = True and onlygen
        varying_beta = False
        if varying_beta:
            betas = [-2, -1, 0, 1, 2]
        else:
            betas = [0]
        for beta in betas:
            output = generate_actions(beta, model, dataset, epoch, parameters,
                                      folder, inter=inter, vertstrans=vertstrans,
                                      nspa=nspa, onlygen=onlygen)
            if varying_beta:
                filename = "generation_beta_{}.npy".format(beta)
            else:
                filename = "generation.npy"

            filename = os.path.join(folder, filename)
            np.save(filename, output)
            print("Saved at: " + filename)


if __name__ == '__main__':
    main()

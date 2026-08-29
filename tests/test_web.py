from bim_evidence_qa.web import select_project_source


def test_no_project_mode_has_no_dataset(synthetic_dataset):
    mode, dataset = select_project_source(
        real_dataset=None,
        has_real_upload=False,
        use_synthetic=False,
        synthetic_dataset=synthetic_dataset,
    )

    assert mode == "No Project"
    assert dataset is None


def test_synthetic_project_mode_is_explicit(synthetic_dataset):
    mode, dataset = select_project_source(
        real_dataset=None,
        has_real_upload=False,
        use_synthetic=True,
        synthetic_dataset=synthetic_dataset,
    )

    assert mode == "Synthetic Development Project"
    assert dataset is synthetic_dataset


def test_real_ifc_takes_priority_over_synthetic_mode(
    synthetic_dataset,
    development_ifc_dataset,
):
    mode, dataset = select_project_source(
        real_dataset=development_ifc_dataset,
        has_real_upload=True,
        use_synthetic=True,
        synthetic_dataset=synthetic_dataset,
    )

    assert mode == "Uploaded Real Project"
    assert dataset is development_ifc_dataset


def test_failed_real_upload_does_not_fall_back_to_synthetic(synthetic_dataset):
    mode, dataset = select_project_source(
        real_dataset=None,
        has_real_upload=True,
        use_synthetic=True,
        synthetic_dataset=synthetic_dataset,
    )

    assert mode == "Uploaded Real Project"
    assert dataset is None

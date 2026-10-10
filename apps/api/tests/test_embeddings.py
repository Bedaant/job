from unittest.mock import MagicMock, patch


def test_embed_texts_returns_none_without_api_key():
    with patch("matching.embeddings.get_settings") as mock_settings:
        mock_settings.return_value.voyage_api_key = None
        from matching.embeddings import embed_texts
        assert embed_texts(["hello"], input_type="document") is None


def test_embed_texts_returns_none_for_empty_list():
    with patch("matching.embeddings.get_settings") as mock_settings:
        mock_settings.return_value.voyage_api_key = "fake-key"
        from matching.embeddings import embed_texts
        assert embed_texts([], input_type="document") is None


@patch("matching.embeddings.voyageai.Client")
@patch("matching.embeddings.get_settings")
def test_embed_texts_calls_voyage_client(mock_settings, mock_client_cls):
    mock_settings.return_value.voyage_api_key = "fake-key"
    mock_client = MagicMock()
    mock_client.embed.return_value = MagicMock(embeddings=[[0.1, 0.2]])
    mock_client_cls.return_value = mock_client

    from matching.embeddings import embed_texts
    result = embed_texts(["hello"], input_type="document")

    assert result == [[0.1, 0.2]]
    mock_client_cls.assert_called_once_with(api_key="fake-key", timeout=60.0)
    mock_client.embed.assert_called_once_with(["hello"], model="voyage-3-lite", input_type="document")


def test_compute_centroid_averages_each_dimension():
    from matching.embeddings import compute_centroid
    assert compute_centroid([[1.0, 2.0], [3.0, 4.0]]) == [2.0, 3.0]


def test_cosine_similarity_identical_vectors_is_one():
    from matching.embeddings import cosine_similarity
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0


def test_cosine_similarity_orthogonal_vectors_is_zero():
    from matching.embeddings import cosine_similarity
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_zero_vector_is_zero_not_a_crash():
    from matching.embeddings import cosine_similarity
    assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0

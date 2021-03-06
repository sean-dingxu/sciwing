import pathlib
from typing import List, Dict, Any, Tuple
import wasabi
import spacy
from spacy.tokens import span
import sciwing.constants as constants
from spacy.gold import biluo_tags_from_offsets
from spacy.gold import offsets_from_biluo_tags

PATHS = constants.PATHS
DATA_DIR = PATHS["DATA_DIR"]


class ScienceIEDataUtils:
    """
        Science-IE is a SemEval Task that is aimed at extracting entities from scientific articles
        This class is a utility for various operations on the competitions data files.
    """

    def __init__(self, folderpath: pathlib.Path, ignore_warnings=False):
        """ Given the folderpath where the ScienceIE data is stored, this class provides various
        utilities. For more information on the dataset you can refer to https://scienceie.github.io/

        Parameters
        ----------
        folderpath : pathlib.Path
            The path where the ScienceIEDataset is stored
        ignore_warnings : bool
            If True, then all the warnings generated by this class for inconsistencies in the
            data is ignored

        """
        self.folderpath = folderpath
        self.ignore_warning = ignore_warnings
        self.entity_types = ["Process", "Material", "Task"]
        self.file_ids = self.get_file_ids()
        self.msg_printer = wasabi.Printer()
        self.nlp = spacy.load("en_core_web_sm")
        self._conll_col_sep = " "

    def get_file_ids(self) -> List[str]:
        """ Get all the file ids from the folder

        Returns
        -------
        List[str]
            A List of File ids in the folder

        """
        file_ids = [file.stem for file in self.folderpath.iterdir()]
        file_ids = set(file_ids)
        file_ids = list(file_ids)
        return file_ids

    def get_text_from_fileid(self, file_id: str) -> str:
        """ Given a file id return the text from the file

        Parameters
        ----------
        file_id : str
            A ScienceIE data file id

        Returns
        -------
        str
            Text read from the file

        """
        path = self.folderpath.joinpath(f"{file_id}.txt")
        with open(path, "r") as fp:
            text = fp.readline()
            text = text.strip()

        return text

    def _get_annotations_for_entity(
        self, file_id: str, entity: str
    ) -> List[Dict[str, Any]]:
        """

        Parameters
        ----------
        file_id : str
            A ScienceIE file id
        entity : str
            One of ``[Task, Process, Material]``

        Returns
        -------
        List[Dict[str, Any]]
            A list of annotations where every annotation is
                start
                    The start character index of the annotation
                end
                    The end character index of the annotation
                words
                    The set of words between the start and the end index
                entity_number
                    The entity number
                tag
                    The tag associated with the set of tags

        """
        annotations = []
        annotation_filepath = self.folderpath.joinpath(f"{file_id}.ann")
        with open(annotation_filepath, "r") as fp:
            for line in fp:
                if line.strip().startswith("T") and len(line.split("\t")) == 3:
                    entity_number, tag_start_end, words = line.split("\t")
                    if len(tag_start_end.split()) != 3:
                        self.msg_printer.warn(
                            f"Skipping LINE:{line} from file_id {file_id} for ENTITY:{entity}",
                            show=not self.ignore_warning,
                        )
                        continue
                    tag, start, end = tag_start_end.split()
                    start = int(start)
                    end = int(end)
                    if tag.lower() == entity.lower():
                        annotation = {
                            "start": start,
                            "end": end,
                            "words": words,
                            "entity_number": entity_number,
                            "tag": tag,
                        }
                        annotations.append(annotation)

        if len(annotations) == 0:
            self.msg_printer.warn(
                f"File {file_id} has 0 annotations for Type {entity}",
                show=not self.ignore_warning,
            )
        return annotations

    def get_bilou_lines_for_entity(self, file_id: str, entity: str):
        """ Writes conll file for the entity type

        Parameters
        ---------------
        file_id : str
            File id of the annotation file
        entity : str
            The entity for which conll file is written

        Returns
        --------
        List[str]
            The list of BILOU lines for the entity

        """
        annotations = self._get_annotations_for_entity(file_id=file_id, entity=entity)
        text = self.get_text_from_fileid(file_id)

        return self._get_bilou_lines_for_entity(
            text=text, annotations=annotations, entity=entity
        )

    def _get_bilou_lines_for_entity(
        self, text: str, annotations: List[Dict[str, Any]], entity: str
    ) -> List[str]:
        """ The list of BILOU lines for entity

        Parameters
        ----------
        text : str
            The text for which BILOU lines need to be returned
        annotations : List[Dict[str, Any]]
            The list of annotations where every annotation is a dictionary
        entity : str
            A particular entity for which the BILOU lines are returned

        Returns
        -------
        List[str]
            The list of BILOU tagged lines, where every line is a ``word, tag, tag, tag`` where
            the tag is decided by the entity.

        """
        entities = []
        for annotation in annotations:
            start = annotation["start"]
            end = annotation["end"]
            tag = annotation["tag"]
            entities.append((start, end, tag))

        doc = self.nlp(text)
        tags = biluo_tags_from_offsets(doc, entities)
        tags = map(
            lambda tag: f"O-{entity}" if tag.startswith("O") or tag == "-" else tag,
            tags,
        )
        tags = list(tags)

        bilou_lines = []

        for token, tag in zip(doc, tags):
            if not token.is_space:
                bilou_line = f"{token.text}{self._conll_col_sep}{self._conll_col_sep.join([tag] * 3)}"
                bilou_lines.append(bilou_line)

        return bilou_lines

    def write_bilou_lines(
        self, out_filename: pathlib.Path, is_sentence_wise: bool = False
    ):
        """ Writes bilou lines in the out_filename for all the files in ``self.folderpath``.
        The output file will contain every word on one line with their tag in BILOU format.

        You can even opt to write the text in a sentence wise. The text which is possibly
        of multiple sentences, is broken down into sentences and then written into the output
        filename. Different sentences are separated by an empty line.

        Parameters
        ----------
        out_filename : pathlib.Path
            The output filename where the conll filename is written
        is_sentence_wise : bool
            You can write the BILOU lines sentence wise. The text in all the ScienceIE files
            will be broken into sentences, and the sentences will be tagged with BILOU tags

        Returns
        -------

        """
        filename_stem = out_filename.stem
        with self.msg_printer.loading(f"Writing BILOU Lines For ScienceIE"):
            for entity_type in self.entity_types:
                out_filename = pathlib.Path(
                    DATA_DIR, f"{filename_stem}_{entity_type.lower()}_conll.txt"
                )
                with open(out_filename, "w") as fp:
                    for file_id in self.file_ids:
                        # split the text into sentences and then write
                        if is_sentence_wise:
                            bilou_lines = self.get_sentence_wise_bilou_lines(
                                file_id=file_id, entity_type=entity_type
                            )
                        else:
                            bilou_lines = self.get_bilou_lines_for_entity(
                                file_id=file_id, entity=entity_type
                            )
                            bilou_lines = [bilou_lines]

                        for line in bilou_lines:
                            fp.write("\n".join(line))
                            fp.write("\n\n")

        self.msg_printer.good("Finished writing BILOU Lines For ScienceIE")

    def get_sentence_wise_bilou_lines(
        self, file_id: str, entity_type: str
    ) -> List[List[str]]:
        """ Get BILOU lines sentence-wise

        Parameters
        ----------
        file_id : str
            File id from ScienceIE Dataset
        entity_type : str
            One of ``['Task', 'Process', 'Material']``

        Returns
        -------
        List[List[str]]
            A list of sentences where every sentence is composed

        """

        annotations = self._get_annotations_for_entity(
            file_id=file_id, entity=entity_type
        )
        text = self.get_text_from_fileid(file_id)

        entities = []
        for annotation in annotations:
            start = annotation["start"]
            end = annotation["end"]
            tag = annotation["tag"]
            entities.append((start, end, tag))

        doc = self.nlp(text)

        # using spacys converter to convert biluo tags from offsets
        tags = biluo_tags_from_offsets(doc, entities)

        # spacy does not provide the O-tags
        # adding it
        # spacy provides a - if there is mismatch between the offsets in the entities
        # and the tokenization. We are mapping it to O in this case
        tags = map(
            lambda tag: f"O-{entity_type}"
            if tag.startswith("O") or tag == "-"
            else tag,
            tags,
        )
        tags = list(tags)

        sentences = []

        # marking the boundaries of sentences
        if not doc[0].is_space:
            current_sent = [f"{doc[0].text} {self._conll_col_sep.join([tags[0]] * 3)}"]
        else:
            current_sent = []

        for tag, token in zip(tags[1:], doc[1:]):
            # if the token is the beginning of a sentence
            # add the currently accumulated sentence to the sentences
            if token.is_sent_start:
                sentences.append(current_sent)

                # avoid adding space to the bilou lines.
                if not token.is_space:
                    current_sent = [
                        f"{token.text}{self._conll_col_sep}{self._conll_col_sep.join([tag] * 3)}"
                    ]

            # if the token is not the start of a sentence
            # THen accumulate the current sentence unitl the next sentence
            else:
                # avoiding situations where space is not there
                if not token.is_space:
                    current_sent.append(
                        f"{token.text}{self._conll_col_sep}{self._conll_col_sep.join([tag] * 3)}"
                    )

        # finally add the last sentence
        sentences.append(current_sent)

        assert len(sentences) == len(list(doc.sents))

        return sentences

    def merge_files(
        self,
        task_filename: pathlib.Path,
        process_filename: pathlib.Path,
        material_filename: pathlib.Path,
        out_filename: pathlib.Path,
    ):
        """ Merge different files to one conll file

        Parameters
        ----------
        task_filename : pathlib.Path
            The CONLL style file having TASK tags
        process_filename : pathlib.Path
            The CONLL style file having Process tags
        material_filename : pathlib.Path
            The CONLL style file having Material Tags
        out_filename : pathlib.Path
            The output file where the different files will be merged
            and every line will consist of ``word Task-tag Process-tag Material-tag``


        """
        with open(task_filename, "r") as task_fp, open(
            process_filename, "r"
        ) as process_fp, open(material_filename, "r") as material_fp, open(
            out_filename, "w"
        ) as out_fp:

            with self.msg_printer.loading("Merging Task Process and Material Files"):
                for task_line, process_line, material_line in zip(
                    task_fp, process_fp, material_fp
                ):
                    if bool(task_line.strip()):
                        word, _, _, task_tag = task_line.strip().split(
                            self._conll_col_sep
                        )
                        word, _, _, process_tag = process_line.strip().split(
                            self._conll_col_sep
                        )
                        word, _, _, material_tag = material_line.strip().split(
                            self._conll_col_sep
                        )
                        out_fp.write(
                            self._conll_col_sep.join(
                                [word, task_tag, process_tag, material_tag]
                            )
                        )
                        out_fp.write("\n")
                    else:
                        out_fp.write("\n")
            self.msg_printer.good("Finished Merging Task Process and Material Files")

    def get_sents(self, text: str) -> List[span.Span]:
        """ Returns all the sentences in the text

        Parameters
        ----------
        text : str

        Returns
        -------
        List[span.Span]
            All the sentences in the text as a spacy span. A spacy span encodes more information
            within

        """
        doc = self.nlp(text)
        sents = doc.sents
        sents = list(sents)
        return sents

    def write_ann_file_from_conll_file(
        self, conll_filepath: pathlib.Path, ann_filepath: pathlib.Path, text: str
    ):
        words = []
        task_tags = []
        process_tags = []
        material_tags = []
        with open(conll_filepath, "r") as fp:
            for line in fp:
                try:
                    word, task_tag, process_tag, material_tag = line.split()
                except ValueError:
                    word = " "
                    task_tag, process_tag, material_tag = line.split()
                words.append(word)
                task_tags.append(task_tag)
                process_tags.append(process_tag)
                material_tags.append(material_tag)

        doc = self.nlp(text)

        task_char_offsets = offsets_from_biluo_tags(doc=doc, tags=task_tags)
        process_char_offsets = offsets_from_biluo_tags(doc=doc, tags=process_tags)
        material_char_offsets = offsets_from_biluo_tags(doc=doc, tags=material_tags)

        ann_lines = []
        term_idx = 0
        for idx, char_offset in enumerate(task_char_offsets):
            id_ = term_idx
            ann_line = self._form_ann_line(
                idx=id_, char_offset=char_offset, tag_name="Task", doc=doc
            )
            ann_lines.append(ann_line)
            term_idx += 1

        for idx, char_offset in enumerate(process_char_offsets):
            id_ = term_idx
            ann_line = self._form_ann_line(
                idx=id_, char_offset=char_offset, tag_name="Process", doc=doc
            )
            ann_lines.append(ann_line)
            term_idx += 1

        for idx, char_offset in enumerate(material_char_offsets):
            id_ = term_idx
            ann_line = self._form_ann_line(
                idx=id_, char_offset=char_offset, tag_name="Material", doc=doc
            )
            ann_lines.append(ann_line)
            term_idx += 1

        with open(ann_filepath, "w") as fp:
            fp.write("\n".join(ann_lines))

    @staticmethod
    def _form_ann_line(
        idx: str,
        char_offset: Tuple[int, int, str],
        tag_name: str,
        doc: spacy.tokens.doc.Doc,
    ):
        """ Forms a ann line that can be used to write the ANN files for CoNLL format

        Parameters
        ----------
        idx : int
            The index for the entity being written
        char_offset : int
            THe start, end, tag for the line
        tag_name : str
            The tag to be used and is one of ``[Task, Process, Material]``
        doc : str
            Spacy doc to query the appropriate characters

        Returns
        -------
        str
            An ANN line that is formed.

        """
        start_offset, end_offset, entity_type = char_offset
        surface_form = doc.char_span(start_offset, end_offset).text
        start_offset = str(start_offset)
        end_offset = str(end_offset)
        ann_line = " ".join([start_offset, end_offset])
        ann_line = "\t".join([ann_line, surface_form])
        ann_line = " ".join([tag_name, ann_line])
        ann_line = "\t".join([f"T{idx}", ann_line])
        return ann_line


if __name__ == "__main__":
    import sciwing.constants as constants

    PATHS = constants.PATHS
    FILES = constants.FILES
    SCIENCE_IE_TRAIN_FOLDER = FILES["SCIENCE_IE_TRAIN_FOLDER"]
    utils = ScienceIEDataUtils(
        folderpath=pathlib.Path(SCIENCE_IE_TRAIN_FOLDER), ignore_warnings=True
    )
    output_filename = pathlib.Path(DATA_DIR, "train.txt")
    utils.write_bilou_lines(out_filename=output_filename, is_sentence_wise=True)

    utils.merge_files(
        pathlib.Path(DATA_DIR, "train_task_conll.txt"),
        pathlib.Path(DATA_DIR, "train_process_conll.txt"),
        pathlib.Path(DATA_DIR, "train_material_conll.txt"),
        pathlib.Path(DATA_DIR, "train_science_ie_conll.txt"),
    )

    SCIENCE_IE_TRAIN_FOLDER = FILES["SCIENCE_IE_DEV_FOLDER"]
    utils = ScienceIEDataUtils(
        folderpath=pathlib.Path(SCIENCE_IE_TRAIN_FOLDER), ignore_warnings=True
    )
    output_filename = pathlib.Path(DATA_DIR, "dev.txt")
    utils.write_bilou_lines(out_filename=output_filename, is_sentence_wise=True)

    utils.merge_files(
        pathlib.Path(DATA_DIR, "dev_task_conll.txt"),
        pathlib.Path(DATA_DIR, "dev_process_conll.txt"),
        pathlib.Path(DATA_DIR, "dev_material_conll.txt"),
        pathlib.Path(DATA_DIR, "dev_science_ie_conll.txt"),
    )

import datetime
import json
import logging
import os
from typing import Any, Generator, Self

import scratchattach as sa


class Meta:
    def __init__(self, author: str, mesg: str, dtime: str, extra=None):
        if extra is None:
            extra = []
        self.author: str = author
        self.mesg: str = mesg
        self.dtime: str = dtime
        self.extra: list = extra
        self.v: str = None
        self.authornick: str = None

    def __str__(self) -> str:
        """
        Create a formatted release/commit message
        """
        return self.authorName() + ": " + self.mesg

    def toData(self) -> dict:
        """
        Convert the metadata in to a dictionary, primarily for JSON conversion
        """
        return {
            "author": self.author,
            "nick": self.authornick,
            "mesg": self.mesg,
            "dtime": self.dtime,
            "extra": self.extra,
            "vers": self.v,
        }

    def assignNick(self, nick: str) -> None:
        """
        Assign an author nickname, in case they desire to be called by a different name
        """
        self.authornick = nick

    def assignRelease(self, vers: str) -> None:
        """
        Assign a meta (and the commit that owns it) to be a release of vers
        """
        self.v = vers

    def isRelease(self) -> bool:
        """
        Checks if the meta (and the commit that owns it) is a release (or at least has the tag)
        """
        if self.v is not None:
            return True
        else:
            return False

    def authorName(self) -> str:
        """
        Gets the author's prefered name, which is either their nickname or their real name
        """
        if self.authornick is not None:
            return self.authornick
        else:
            return self.author

    @classmethod
    def fromDict(cls, data: dict) -> Meta:
        """
        Create a meta from a dictionary of data
        """
        meta = cls(data["author"], data["mesg"], data["dtime"], data["extra"])
        meta.assignNick(data["nick"])
        if data["vers"] is not None:
            meta.assignRelease(data["vers"])
        return meta


class Commit:
    def __init__(self, blob: str, meta: Meta, cid: int):
        self.blob: str = blob
        self.meta: Meta = meta
        self.prev: Commit = None
        self.next: Commit = None
        self.cid = cid

    def __str__(self) -> str:
        return str(self.meta)

    def toData(self) -> dict:
        """
        Convert the commit into a dictionary, designed for JSON coversion
        """
        cprev = self.prev.cid if self.prev is not None else None
        cnext = self.next.cid if self.next is not None else None
        return {
            self.cid: {
                "meta": self.meta.toData(),
                "prev": cprev,
                "next": cnext,
                "blob": self.blob,
            }
        }

    def setPrev(self, cprev: Commit) -> None:
        """
        Set the previous commit in the linked list
        """
        self.prev = cprev

    def getPrev(self, dist: int = 1) -> Commit:
        """
        Get the commit dist from the current commit, going backwards through the chain
        """
        current = self
        for i in range(dist + 1):
            if current.prev is not None:
                current = current.prev
            else:
                raise IndexError("Jumped backwards out of Commit list")
        return current

    def walkPrev(self) -> Generator[Self | Commit, Any, None]:
        """
        Walk the previous commits (including the current one) to the first commit in the chain
        """
        current = self
        while True:
            yield current
            if current.prev is not None:
                current = current.prev
            else:
                break

    def setNext(self, cnext: Commit) -> None:
        """
        Set the next commit in the linked list
        """
        self.next = cnext

    def getNext(self, dist: int = 1) -> Commit:
        """
        Get the commit dist away from the current commit, going forwards through the chain
        """
        current = self
        for i in range(dist + 1):
            if current.next is not None:
                current = current.next
            else:
                raise IndexError("Jumped forwards out of Commit list")
        return current

    def walkNext(self) -> Generator[Self | Commit, Any, None]:
        """
        Walk the next commits (including the current one) to the last commit in the chain
        """
        current = self
        while True:
            yield current
            if current.next is not None:
                current = current.next
            else:
                break

    @classmethod
    def fromDict(cls, cid: str, data: dict) -> Commit:
        """
        Make a commit from a dictionary of data and a commit id
        """
        meta = Meta.fromDict(data["meta"])
        commit = cls(data["blob"], meta, int(cid))
        return commit


class ItchyVersioning:
    """
    Class that holds the majority of the highlevel functions dealing with the creation and management of the VCS
    """

    def __init__(self, user: str, passwd: str, project: str, vcs_dir: str):
        if not os.path.exists(vcs_dir):
            os.mkdir(vcs_dir)
            os.mkdir(vcs_dir + "/blobs")
        # TODO: Allow sessionid auth, alolow other method of providing user/passwd
        self.sas = sa.login(user, passwd)
        self.prjid = project
        self.prj = self.sas.connect_project(int(project))
        self.log = logging.getLogger(f"ItchyVersioning-{project}")
        self.head = None
        self.dir = vcs_dir

    def _getProjectFile(self) -> str | None:
        """
        Grab the project file with name of isoformated time of download
        """
        try:
            self.log.info("Downloading project file")
            fname = datetime.datetime.now().isoformat()
            self.prj.download(filename=fname, dir=self.dir + "/blobs")
            return self.dir + "/blobs/" + fname + ".sb3"
        except e:
            self.log.error("Download of the project file failed")

    def _appendInstruction(self, mesg: str, top: bool = True) -> None:
        """
        Append the instructions on the Scratch share page
        """
        self.log.info("Appending %s to instructions (at the top? %s)", mesg, top)
        self.prj.update()
        if not top:
            self.prj.set_instructions(self.prj.instructions + "\n" + mesg)
        else:
            self.prj.set_instructions(mesg + self.prj.instructions)

    def _appendNotes(self, mesg: str, top: bool = True) -> None:
        """
        Append the notes on the Scratch share page
        """
        self.log.info("Appending %s to notes (at the top? %s)", mesg, top)
        self.prj.update()
        if not top:
            self.prj.set_notes(self.prj.notes + "\n" + mesg)
        else:
            self.prj.set_notes(mesg + self.prj.notes)

    def _commit(self, blob: str, author: str, mesg: str, extra: list) -> None:
        """
        Create a commit with the data and add it to the VCS
        """
        meta = Meta(author, mesg, datetime.datetime.now().isoformat(), extra)
        if self.head is None:
            self.head = Commit(blob, meta, 0)
            self.log.info(f"Created initial commit by {author}")
        else:
            commit = Commit(blob, meta, self.head.cid + 1)
            commit.setPrev(self.head)
            self.head.setNext(commit)
            self.head = commit
            self.log.info(f"Created commit by {author}")

    def _addCommitMesg(self, rmesg: str, commit: Commit) -> str:
        """
        Add a commit message from a Meta object to a str object
        """
        rmesg = rmesg + " - " + str(commit) + "\n"
        return rmesg

    def createCommit(self, author: str, mesg: str, meta: list) -> None:
        """
        Highlevel command to create a commit from the Scratch project
        """
        blobpath = self._getProjectFile()
        self._commit(blobpath, author, mesg, meta)

    def createRelease(self, vers: str, inst: bool = True, top: bool = True) -> None:
        """
        Create a release of the specified version, with changelog of commit messages going back to the last release, and add it to either the top or bottom of instructions or notes on the Scratch page
        """
        mesg = vers + "\n"
        self.head.meta.assignRelease(vers)
        for commit in self.head.walkPrev():
            if not commit.meta.isRelease() and commit != self.head:
                mesg = self._addCommitMesg(mesg, commit.meta)
            else:
                break
        if inst:
            self._appendInstruction(mesg, top)
        else:
            self._appendNotes(mesg, top)

    def syncCommits(self) -> None:
        """
        Sync commit history to a file so it can be persisted across instances
        """
        if self.head is None and not os.path.exists(self.dir + "/commitHistory"):
            return
        commitdata = {}
        for commit in self.head.walkPrev():
            commitdata.update(commit.toData())
        vcsdata = {
            "project": self.prjid,
            "vcsDir": self.dir,
            "syncDate": datetime.datetime.now().isoformat(),
            "commits": commitdata,
        }
        with open(self.dir + "/commitHistory", "w") as cHist:
            json.dump(vcsdata, cHist)

    @classmethod
    def fromFile(cls, user: str, passwd: str, file: str) -> ItchyVersioning:
        """
        Create a VCS file from a commitHistory file with project data
        """
        with open(file, "r") as jsonFile:
            vcsData = json.load(jsonFile)
        vcs = cls(user, passwd, vcsData["project"], vcsData["vcsDir"])
        for cid, cdata in reversed(vcsData["commits"].items()):
            if cdata["prev"] is None:
                vcs.head = Commit.fromDict(cid, cdata)
            else:
                commit = Commit.fromDict(cid, cdata)
                commit.prev = vcs.head
                vcs.head.next = commit
                vcs.head = commit
        return vcs

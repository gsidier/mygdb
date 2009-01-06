

class GdbCommandBuilder(object):
	def _send(self, command, token = None, *args, **kwargs):
		raise NotImplementedError()

	def quit(self):	
		return self._send("quit")
	# Breakpoint Commands
	def break_after(self, bp, count, token = None, *args, **kwargs):
		return self._send("-break-after %d %d" % (bp, count), token, *args, **kwargs)
	def break_condition(self, bp, cond, token = None, *args, **kwargs):
		return self._send("-break-condition %d %s" % (bp, cond), token, *args, **kwargs)
	def break_delete(self, bps, token = None, *args, **kwargs):
		return self._send("-break-delete %s" % (' '.join(bps) if hasattr(bps, '__getitem__') else str(bps)), token, *args, **kwargs)
	def break_disable(self, bps, token = None, *args, **kwargs):
		return self._send("-break-disable %s" % (' '.join(bps) if hasattr(bps, '__getitem__') else str(bps)), token, *args, **kwargs)
	def break_enable(self, bps, token = None, *args, **kwargs):
		return self._send("-break-enable %s" % (' '.join(bps) if hasattr(bps, '__getitem__') else str(bps)), token, *args, **kwargs)
	def break_info(self, bp, token = None, *args, **kwargs):
		return self._send("-break-enable %d" % bp, token, *args, **kwargs)
	def break_insert(self, loc = None, cond = None, temp = False, hardware = False, count = None, thread = None, force = False, token = None, *args, **kwargs):
		return self._send(
			"-break-insert %s %s %s %s %s %s %s" % (
				'-t' if temp else '',
				'-h' if hardware else '',
				'-f' if force else '',
				"-c %s" % cond if cond is not None else '',
				"-i %d" % count if count else '',
				"-p %d" % thread if thread else '',
				loc if loc is not None else ''
			), 
		token, *args, **kwargs)
	def info_break(self, token = None, *args, **kwargs):
		return self._send("-break-list", token, *args, **kwargs)
	def watch(self, expr, type = None, token = None, *args, **kwargs):
		return self._send("-break-watch %s %s" % ("-%s" % type if type else '', expr), token, *args, **kwargs)
	# Program Context [TODO:incomplete]
	def cd(self, dir, token = None, *args, **kwargs):
		return self._send("-environment-cd %s" % dir, token, *args, **kwargs)
	def pwd(self, token = None, *args, **kwargs):
		return self._send("-environment-pwd", token, *args, **kwargs)
	# Thread Commands [TODO]
	# Program Execution
	def cont(self, token = None, *args, **kwargs):
		return self._send("-exec-continue", token, *args, **kwargs)
	def finish(self, token = None, *args, **kwargs):
		return self._send("-exec-finish", token, *args, **kwargs)
	def interrupt(self, token = None, *args, **kwargs):
		return self._send("-exec-interrupt", token, *args, **kwargs)
	def next(self, token = None, *args, **kwargs):
		return self._send("-exec-next", token, *args, **kwargs)
	def nexti(self, token = None, *args, **kwargs):
		return self._send("-exec-next-instruction", token, *args, **kwargs)
	def ret(self, token = None, *args, **kwargs):
		return self._send("-exec-return", token, *args, **kwargs)
	def run(self, token = None, *args, **kwargs):
		return self._send("-exec-run", token, *args, **kwargs)
	def step(self, token = None, *args, **kwargs):
		return self._send("-exec-step", token, *args, **kwargs)
	def stepi(self, token = None, *args, **kwargs):
		return self._send("-exec-step-instruction", token, *args, **kwargs)
	def until(self, loc = None, token = None, *args, **kwargs):
		return self._send("-exec-until %s" % (loc if loc is not None else ''), token, *args, **kwargs)
	# Stack Manipulation Commands [TODO]
	def info_frame(self, token = None, *args, **kwargs):
		return self._send("-stack-info-frame", token, *args, **kwargs)
	def stack_depth(self, maxdepth = None, token = None, *args, **kwargs):
		return self._send("-stack-info-depth %s" % (maxdepth if maxdepth is not None else ''), token, *args, **kwargs)
	def stack_list_args(self, showvals = False, lo = None, hi = None, token = None, *args, **kwargs):
		return self._send("-stack-list-arguments %d %s" % ((1 if showvals else 0), "%d %d" % (lo, hi) if lo is not None and hi is not None else ''), token, *args, **kwargs) 
	def list_frames(self, lo = None, hi = None, token = None, *args, **kwargs):
		return self._send("-stack-list-frames %s" % ("%d %d" % (lo, hi) if lo is not None and hi is not None else ""), token, *args, **kwargs)
	def list_locals(self, showvals = False, token = None, *args, **kwargs):
		return self._send("-stack-list-locals %d" % (1 if showvals else 0), token, *args, **kwargs)
	def select_frame(self, frame, token = None, *args, **kwargs):
		return self._send("-stack-select-frame %d" % frame, token, *args, **kwargs)
	# Variable Objects 
	def var_create(self, expr, name = None, frame = None, token = None, *args, **kwargs):
		if name is None:
			name = '-'
		if frame is None:
			frame = '*'
		return self._send("-var-create %s %s %s" % (name, frame, expr), token , *args, **kwargs)
	def var_delete(self, name, token = None, *args, **kwargs):
		return self._send("-var-delete %s" % name, token, *args, **kwargs)
	def var_set_format(self, name, format, token = None, *args, **kwargs):
		return self._send("-var-set-format %s %s" % (name, format), token, *args, **kwargs)
	def var_show_format(self, name, token = None, *args, **kwargs):
		return self._send("-var-show-format %s" % name, token, *args, **kwargs)
	def var_num_children(self, name, token = None, *args, **kwargs):
		return self._send("-var-info-num-children %s" % name, token, *args, **kwargs)
	def var_list_children(self, name, token = None, *args, **kwargs):
		return self._send("-var-list-children %s" % name, token, *args, **kwargs)
	def var_type(self, name, token = None, *args, **kwargs):
		return self._send("-var-info-type %s" % name, token, *args, **kwargs)
	def var_path_expr(self, name, token = None, *args, **kwargs):
		return self._send("-var-info-path-expression %s" % name, token, *args, **kwargs)
	def var_attributes(self, name, token = None, *args, **kwargs):
		return self._send("-var-show-attributes %s" % name, token, *args, **kwargs)
	def var_eval(self, name, token = None, *args, **kwargs):
		return self._send("-var-evaluate-expression %s" % name, token, *args, **kwargs)
	def var_assign(self, name, expr, token = None, *args, **kwargs):
		return self._send("-var-assign %s %s" % (name, expr), token, *args, **kwargs)
	def var_update(self, name = None, print_values = "--all-values", token = None, *args, **kwargs):
		return self._send("-var-update %s %s" % (print_values, name if name else '*'), token, *args, **kwargs)
	def var_set_frozen(self, name, flag = 1, token = None, *args, **kwargs):
		return self._send("-var-set-frozen %s %s" % (name, flag), token, *args, **kwargs)
	# Data Manipulation
	def data_disassemble(self, start_addr = None, end_addr = None, filename = None, line = None, nlines = None, mode = 0, token = None, *args, **kwargs):
		if start_addr is not None and end_addr is not None:
			addrspec = "-s %s -e %s" % (start_addr, end_addr)
		else:
			addrspec = ""
		if filename is not None and line is not None:
			filespec = "-f %s -l %s" % (filename, line)
			if nlines is not None:
				filespec += " -n %s" % nlines
		else:
			filespec = ""
		return self._send("-data-disassemble %s %s -- %d" % (addrspec, filespec, mode), token, *args, **kwargs)
	def data_eval(self, expr, token = None, *args, **kwargs):
		return self._send("-data-evaluate-expression %s" % expr, token, *args, **kwargs)
	def data_list_changed_regs(self, token = None, *args, **kwargs):
		return self._send("-data-list-changed-registers", token, *args, **kwargs)
	def data_list_reg_names(self, token = None, *args, **kwargs):
		return self._send("-data-list-register-names", token, *args, **kwargs)
	def data_list_reg_values(self, format, regs = None, token = None, *args, **kwargs):
		regspec = "" if regs is None else ' '.join(str(r) for r in regs)
		return self._send("-data-list-register-values %s %s" % (format, regspec), token, *args, **kwargs)
	def data_read_mem(self, addr, format, word_size, nrows, ncols, byte_offset = None, aschar = None, token = None, *args, **kwargs):
		offsetspec = "" if offset is None else "-o %s" % byte_offset
		ascharspec = "" if aschar is None else str(aschar)
		return self._send("-data-read-memory %s %s %s %s %s %s %s" % (offsetspec, addr, format, word_size, nrows, ncols, ascharspec), token, *args, **kwargs)
	# Tracepoint Commands [TODO]
	# Symbol Query Commands [TODO]
	# File Commands [TODO:incomplete]
	def file(self, file, token = None, *args, **kwargs):
		return self._send("-file-exec-and-symbols %s" % file, token, *args, **kwargs)
	def exec_file(self, file, token = None, *args, **kwargs):
		return self._send("-file-exec-file %s" % file, token, *args, **kwargs)
	def info_sections(self, file, token = None, *args, **kwargs):
		return self._send("-file-list-exec-sections", token, *args, **kwargs)
	def info_source(self, token = None, *args, **kwargs):
		return self._send("-file-list-exec-source-file", token, *args, **kwargs)
	def info_sources(self, token = None, *args, **kwargs):
		return self._send("-file-list-exec-source-files", token, *args, **kwargs)
	def info_shared(self, token = None, *args, **kwargs):
		return self._send("-file-list-shared-libraries", token, *args, **kwargs)
	def info_symbol_files(self, token = None, *args, **kwargs):
		return self._send("-file-list-symbol-files", token, *args, **kwargs)
	def symbol_file(self, file, token = None, *args, **kwargs):
		return self._send("-file-symbol-file %s" % file, token, *args, **kwargs)
	# Target Manipulation Commands
	def target_attach(self, target, token = None, *args, **kwargs):
		return self._send("-target-attach %s" % target, token, *args, **kwargs)
	def target_compare_sections(self, section = None, *args, **kwargs):
		return self._send("-target-compare-sections %s" % ('' if section is None else section), token, *args, **kwargs)
	def target_detach(self, token = None, *args, **kwargs):
		return self._send("-target-detach", token, *args, **kwargs)
	def target_disconnect(self, token = None, *args, **kwargs):
		return self._send("-target-disconnect", token, *args, **kwargs)
	def target_download(self, token = None, *args, **kwargs):
		return self._send("-target-download", token, *args, **kwargs)
	def target_exec_status(self, token = None, *args, **kwargs):
		return self._send("-target-exec-status", token, *args, **kwargs)
	def target_list_available_targets(self, token = None, *args, **kwargs):
		return self._send("-target-list-available-targets", token, *args, **kwargs)
	def target_list_current_targets(self, token = None, *args, **kwargs):
		return self._send("-target-list-current-targets", token, *args, **kwargs)
	def target_list_params(self, token = None, *args, **kwargs):
		return self._send("-target-list-parameters", token, *args, **kwargs)
	def target_select(self, type, params = [], token = None, *args, **kwargs):
		return self._send("-target select %s %s" % (type, ' '.join(params)), token, *args, **kwargs)
	# File Transfer Commands [TODO]
	# Misc Commands
	def exit(self, token = None, *args, **kwargs):
		return self._send("-gdb-exit", token, *args, **kwargs)



import piped_event
import sys

def echo(s):
	print s

if __name__ == '__main__':
	
	if len(sys.argv) != 2:
		print "USAGE: %s <named pipe>" % sys.argv[0]
		
	fifo_path = sys.argv[1]

	fifo = file(fifo_path, 'r')

	evt_client = piped_event.ClientSideObserver(fifo)
	evt_client.add_handler('onProcessedResponse', lambda : echo("Processed response"))
	print "Waiting..."
	evt_client.process()

